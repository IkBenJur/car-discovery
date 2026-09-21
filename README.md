# __PROJECT_NAME__

Base repo for Go + React projects.

## Start

```bash
# 0. Init (once, after forking/cloning): renames placeholders, installs deps, sets up git
python3 scripts/init.py "My Project"

# 1. Database
cd backend && docker compose up -d

# 2. Backend
cp .env.example .env
go run ./cmd
# -> http://localhost:8080

# 3. Frontend
cd ../frontend
cp .env.example .env
npm install
npm run dev
# -> http://localhost:5173
```

## Backend

- Entry point: `cmd/main.go` + `cmd/api.go`
- DB migrations run automatically on startup (`internal/postgres/migrations`, goose)
- Queries are sqlc-generated from `internal/postgres/sqlc/*.sql` — edit the `.sql`, then run `sqlc generate`, never edit generated files
- `internal/auth` = password hashing + JWT; `internal/middleware/auth.go` = `RequireAuth` middleware
- `GET /health` for liveness
- Config via env vars, see `.env.example`

## Frontend

- React Router v7, framework mode, SPA (`ssr: false`) — no server rendering
- Tailwind v4 via `@tailwindcss/vite`, no component library
- Folder convention: `components/`, `hooks/`, `routes/`, `services/`, `types/`, `lib/`
- Data fetching = TanStack Query; API calls go through `lib/apiClient.ts`
- Auth token stored in `localStorage` (`lib/auth.ts`)
- `VITE_API_URL` in `.env` points at the backend

## Build

- `build/Dockerfile.backend` — multi-stage Go build, alpine runtime
- `build/Dockerfile.frontend` — multi-stage Node build, served via `react-router-serve` (`npm run start`)
- Build both from the repo root: `docker build -f build/Dockerfile.backend .` / `docker build -f build/Dockerfile.frontend .`

## Tech stack

**Backend:** Go, Gin, pgx, goose, sqlc, golang-jwt, bcrypt, Postgres

**Frontend:** React, React Router v7, TypeScript, Vite, Tailwind CSS v4, TanStack Query

**Build:** Docker, docker compose
