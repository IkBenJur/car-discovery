---
name: add-entity
description: Scaffold a new full-stack CRUD entity for this repo (Go + Gin + SQLC + Postgres backend, React Router + TanStack Query frontend) - migration, SQLC queries, Go handler, route wiring, frontend types, service, and hooks. Use when the user asks to add a new entity, resource, model, or CRUD feature to this project (e.g. "add a Post entity", "create a Task resource with title and done fields", "scaffold a Comment model").
---

# Add Entity

Scaffolds a complete, working CRUD slice for a new entity: Postgres table, SQLC
queries, Go handler + routes on the backend; TypeScript types, a service, and
React Query hooks on the frontend. Follows the exact conventions already used
by the `users` entity in this repo - read `backend/internal/users/handler.go`
and `backend/internal/postgres/sqlc/user_queries.sql` alongside this skill if
anything below is ambiguous; they are the canonical example.

**Out of scope** (do not generate these unless separately asked):
- Frontend routes, pages, or components. This skill stops at types/service/hooks.
- Ownership scoping (e.g. a `user_id` foreign key limiting rows to the logged-in
  user). Generated entities are global resources unless the field list says
  otherwise.

## 1. Parse the request

You need:
- **Entity name**: a singular, lowercase noun (e.g. `post`, `task`, `comment`).
  If the user gives a different case or plural, normalize it and confirm.
- **Fields**: a list of `name:type` pairs (e.g. `title:string body:string?
  published:bool`). A trailing `?` marks the field nullable/optional. If the
  user described the entity in prose ("a post with a title, body, and a
  published flag") instead of this syntax, translate it yourself - don't make
  the user rewrite it.
- **Visibility**: protected (default - mounted behind the existing
  `RequireAuth` middleware) unless the user says "public".

If the plural form of the entity name is irregular (`person` -> `people`,
`child` -> `children`), ask the user for the correct plural/table name instead
of guessing. Regular pluralization (append `s`; `y` -> `ies` after a
consonant; `s`/`x`/`z`/`ch`/`sh` -> `es`) needs no confirmation.

**Before generating anything**, check whether `backend/internal/<entities>/`
already exists. If it does, stop and ask the user how they want to proceed
(add fields to the existing entity vs. this being a naming collision) instead
of overwriting it.

## 2. Field type mapping

| Input type | Postgres column | Go type (non-null) | Go type (nullable, `?`) | TS type |
|---|---|---|---|---|
| `string` / `text` | `TEXT` | `string` | `pgtype.Text` | `string` |
| `int` | `INT` | `int32` | `pgtype.Int4` | `number` |
| `float` | `DOUBLE PRECISION` | `float64` | `pgtype.Float8` | `number` |
| `bool` | `BOOLEAN` | `bool` | `pgtype.Bool` | `boolean` |
| `uuid` | `UUID` | `pgtype.UUID` | `pgtype.UUID` | `string` |
| `timestamp` | `TIMESTAMP` | `pgtype.Timestamp` | `pgtype.Timestamp` | `string` |

SQLC (pgx/v5 mode, already configured in `backend/sqlc.yml`) infers the Go
type automatically from column nullability - you only need to get the SQL
column definition right (`NOT NULL` for required fields, nothing for
optional). Nullable fields need `.String`/`.Int32`/`.Bool` + `.Valid` when
read in Go and are JSON-marshalled as their pgtype wrapper - mention this to
the user if they add optional fields, since the handler's response struct
needs to unwrap them (e.g. `Body: post.Body.String`).

**Every table gets `id`, `created_at`, and `updated_at` in addition to the
requested fields.** This is non-negotiable - it matches the `users` table and
every future table must follow it.

## 3. Naming conventions

For entity `post` (fields `title:string`, `body:string?`, `published:bool`):

| Artifact | Path / name |
|---|---|
| Migration | `backend/internal/postgres/migrations/{next_number}_create_posts.sql` |
| SQLC queries | `backend/internal/postgres/sqlc/post_queries.sql` |
| Go package | `backend/internal/posts/handler.go` |
| Table | `posts` |
| Route base | `/posts`, `/posts/:id` |
| Frontend types | `frontend/app/types/post.types.ts` |
| Frontend service | `frontend/app/services/post.service.ts` |
| Frontend query hooks | `frontend/app/hooks/usePosts.ts` |
| Frontend mutation hooks | `frontend/app/hooks/useCreatePost.ts`, `useUpdatePost.ts`, `useDeletePost.ts` |

Go query/method names: `CreatePost`, `FindPostById`, `ListPosts`,
`UpdatePost`, `DeletePost`. Handler methods: `Create`, `List`, `FindById`,
`Update`, `Delete`.

To find `{next_number}`, list `backend/internal/postgres/migrations/*.sql`,
take the highest existing prefix, and zero-pad the next integer to 5 digits
(the existing file is `00001_create_users.sql`, so the next one is
`00002_...`).

## 4. Backend

### 4a. Migration

`backend/internal/postgres/migrations/{next_number}_create_posts.sql`:

```sql
-- +goose Up
CREATE TABLE IF NOT EXISTS posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    body TEXT,
    published BOOLEAN NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

-- +goose Down
DROP TABLE posts;
```

### 4b. SQLC queries

`backend/internal/postgres/sqlc/post_queries.sql`:

```sql
-- name: CreatePost :one
INSERT INTO posts (title, body, published)
VALUES ($1, $2, $3)
RETURNING *;

-- name: FindPostById :one
SELECT * FROM posts
WHERE id = $1;

-- name: ListPosts :many
SELECT * FROM posts
ORDER BY created_at DESC;

-- name: UpdatePost :one
UPDATE posts
SET title = $2, body = $3, published = $4, updated_at = now()
WHERE id = $1
RETURNING *;

-- name: DeletePost :exec
DELETE FROM posts
WHERE id = $1;
```

The `UPDATE` query must always set `updated_at = now()` explicitly - Postgres
does not do this automatically.

After writing both files, run from `backend/`:

```bash
sqlc generate
```

This regenerates `internal/postgres/sqlc/models.go` (adds the `Post` struct),
`querier.go` (adds the five methods to the `Querier` interface), and
`post_queries.sql.go`. **Never hand-edit these generated files.**

### 4c. Handler

`backend/internal/posts/handler.go`, following `internal/users/handler.go`'s
idioms exactly (module path below is whatever `backend/go.mod` currently
declares - read it, don't assume):

`body` is nullable (`body:string?`), so SQLC generated `pgtype.Text` for it -
notice `pgtype.Text{String: ..., Valid: ...}` on write and `.String` on read
below. A non-nullable field (`title`, `published`) binds directly as its
plain Go type with no wrapping.

```go
package posts

import (
	"net/http"

	"github.com/IkBenJur/<module>/internal/json"
	repo "github.com/IkBenJur/<module>/internal/postgres/sqlc"
	"github.com/IkBenJur/<module>/internal/utils"
	"github.com/gin-gonic/gin"
	"github.com/jackc/pgx/v5/pgtype"
)

type Handler struct {
	Queries repo.Querier
}

func NewHandler(queries repo.Querier) *Handler {
	return &Handler{Queries: queries}
}

type createPostRequest struct {
	Title     string `json:"title" binding:"required"`
	Body      string `json:"body"`
	Published bool   `json:"published"`
}

type updatePostRequest struct {
	Title     string `json:"title" binding:"required"`
	Body      string `json:"body"`
	Published bool   `json:"published"`
}

type postResponse struct {
	ID        string `json:"id"`
	Title     string `json:"title"`
	Body      string `json:"body"`
	Published bool   `json:"published"`
}

func toPostResponse(post repo.Post) postResponse {
	return postResponse{
		ID:        utils.UUIDString(post.ID),
		Title:     post.Title,
		Body:      post.Body.String,
		Published: post.Published,
	}
}

func (h *Handler) Create(c *gin.Context) {
	var req createPostRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		json.WriteError(c, http.StatusBadRequest, err)
		return
	}

	post, err := h.Queries.CreatePost(c, repo.CreatePostParams{
		Title:     req.Title,
		Body:      pgtype.Text{String: req.Body, Valid: req.Body != ""},
		Published: req.Published,
	})
	if err != nil {
		json.WriteErrorFromStringWithErrorObjectLog(c, http.StatusInternalServerError, "failed to create post", err)
		return
	}

	json.WriteJSON(c, http.StatusCreated, toPostResponse(post))
}

func (h *Handler) List(c *gin.Context) {
	posts, err := h.Queries.ListPosts(c)
	if err != nil {
		json.WriteErrorFromStringWithErrorObjectLog(c, http.StatusInternalServerError, "failed to list posts", err)
		return
	}

	response := make([]postResponse, len(posts))
	for i, post := range posts {
		response[i] = toPostResponse(post)
	}

	json.WriteJSON(c, http.StatusOK, response)
}

func (h *Handler) FindById(c *gin.Context) {
	id, err := utils.ParseUUID(c.Param("id"))
	if err != nil {
		json.WriteErrorFromString(c, http.StatusBadRequest, "invalid id")
		return
	}

	post, err := h.Queries.FindPostById(c, id)
	if err != nil {
		json.WriteErrorFromStringWithErrorObjectLog(c, http.StatusNotFound, "post not found", err)
		return
	}

	json.WriteJSON(c, http.StatusOK, toPostResponse(post))
}

func (h *Handler) Update(c *gin.Context) {
	id, err := utils.ParseUUID(c.Param("id"))
	if err != nil {
		json.WriteErrorFromString(c, http.StatusBadRequest, "invalid id")
		return
	}

	var req updatePostRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		json.WriteError(c, http.StatusBadRequest, err)
		return
	}

	post, err := h.Queries.UpdatePost(c, repo.UpdatePostParams{
		ID:        id,
		Title:     req.Title,
		Body:      pgtype.Text{String: req.Body, Valid: req.Body != ""},
		Published: req.Published,
	})
	if err != nil {
		json.WriteErrorFromStringWithErrorObjectLog(c, http.StatusInternalServerError, "failed to update post", err)
		return
	}

	json.WriteJSON(c, http.StatusOK, toPostResponse(post))
}

func (h *Handler) Delete(c *gin.Context) {
	id, err := utils.ParseUUID(c.Param("id"))
	if err != nil {
		json.WriteErrorFromString(c, http.StatusBadRequest, "invalid id")
		return
	}

	if err := h.Queries.DeletePost(c, id); err != nil {
		json.WriteErrorFromStringWithErrorObjectLog(c, http.StatusInternalServerError, "failed to delete post", err)
		return
	}

	c.Status(http.StatusNoContent)
}
```

Field-count changes (structs, params, `toPostResponse`) obviously scale with
however many fields the user asked for - the shape above is the pattern, not
a fixed template.

### 4d. Route wiring

Edit `backend/cmd/api.go`. Import the new package, instantiate its handler,
and register routes. Protected (default) goes on the existing `authorized`
group; public goes at the top level next to `/auth/register`:

```go
postHandler := posts.NewHandler(app.Queries)
authorized.POST("posts", postHandler.Create)
authorized.GET("posts", postHandler.List)
authorized.GET("posts/:id", postHandler.FindById)
authorized.PUT("posts/:id", postHandler.Update)
authorized.DELETE("posts/:id", postHandler.Delete)
```

### 4e. Verify

From `backend/`:

```bash
gofmt -w cmd/api.go
go build ./...
```

`gofmt -w` re-sorts the import block you just hand-edited (import order
depends on the entity name vs. `postgres/sqlc` alphabetically - don't try to
guess it, just run `gofmt -w`). Fix anything that doesn't compile before
moving to the frontend.

## 5. Frontend

### 5a. Types

`frontend/app/types/post.types.ts`:

```typescript
export interface Post {
  id: string;
  title: string;
  body: string;
  published: boolean;
  created_at: string;
  updated_at: string;
}

export type CreatePostDto = Pick<Post, "title" | "body" | "published">;
export type UpdatePostDto = CreatePostDto;
```

### 5b. Service

`frontend/app/services/post.service.ts`:

```typescript
import { apiClient } from "~/lib/apiClient";
import type { CreatePostDto, Post, UpdatePostDto } from "~/types/post.types";

export const postService = {
  getAll(): Promise<Post[]> {
    return apiClient.get<Post[]>("/posts");
  },

  getById(id: string): Promise<Post> {
    return apiClient.get<Post>(`/posts/${id}`);
  },

  create(dto: CreatePostDto): Promise<Post> {
    return apiClient.post<Post>("/posts", dto);
  },

  update(id: string, dto: UpdatePostDto): Promise<Post> {
    return apiClient.put<Post>(`/posts/${id}`, dto);
  },

  delete(id: string): Promise<void> {
    return apiClient.delete<void>(`/posts/${id}`);
  },
};
```

### 5c. Hooks

One file grouping both queries, one file per mutation - matching
`useCurrentUser.ts` (plain `useQuery`, not `useSuspenseQuery` - this repo does
not use Suspense boundaries) and `useLogin.ts`.

`frontend/app/hooks/usePosts.ts`:

```typescript
import { useQuery } from "@tanstack/react-query";
import { postService } from "~/services/post.service";

export function usePosts() {
  return useQuery({
    queryKey: ["posts"],
    queryFn: () => postService.getAll(),
  });
}

export function usePost(id: string) {
  return useQuery({
    queryKey: ["posts", id],
    queryFn: () => postService.getById(id),
    enabled: Boolean(id),
  });
}
```

`frontend/app/hooks/useCreatePost.ts`:

```typescript
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { postService } from "~/services/post.service";
import type { CreatePostDto } from "~/types/post.types";

export function useCreatePost() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (dto: CreatePostDto) => postService.create(dto),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["posts"] });
    },
  });
}
```

`frontend/app/hooks/useUpdatePost.ts`:

```typescript
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { postService } from "~/services/post.service";
import type { UpdatePostDto } from "~/types/post.types";

export function useUpdatePost(id: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (dto: UpdatePostDto) => postService.update(id, dto),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["posts"] });
      queryClient.invalidateQueries({ queryKey: ["posts", id] });
    },
  });
}
```

`frontend/app/hooks/useDeletePost.ts`:

```typescript
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { postService } from "~/services/post.service";

export function useDeletePost() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => postService.delete(id),
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: ["posts"] });
      queryClient.removeQueries({ queryKey: ["posts", id] });
    },
  });
}
```

### 5d. Verify

From `frontend/`:

```bash
npm run typecheck
```

## 6. Finish

Report back to the user with the list of files created/edited and remind them
that no UI (routes/pages/components) was generated - wiring the new hooks
into a page is a separate step.

### Checklist

- [ ] Existing `backend/internal/<entities>/` checked for collisions first
- [ ] Migration created with `id`, requested fields, `created_at`, `updated_at`
- [ ] SQLC queries file created; `UPDATE` sets `updated_at = now()`
- [ ] `sqlc generate` run from `backend/`
- [ ] Handler created with Create/List/FindById/Update/Delete
- [ ] Routes wired in `cmd/api.go` (protected by default)
- [ ] `go build ./...` passes
- [ ] Frontend types file created (`Entity`, `CreateEntityDto`, `UpdateEntityDto`)
- [ ] Frontend service file created (all five methods)
- [ ] Query hook file created (list + by-id, plain `useQuery`)
- [ ] Three mutation hook files created, each invalidating the right query keys
- [ ] `npm run typecheck` passes
- [ ] No routes/pages/components generated unless separately asked
