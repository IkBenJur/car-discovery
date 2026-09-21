package middleware

import (
	"net/http"
	"strings"

	"github.com/IkBenJur/__PROJECT_SLUG__/internal/auth"
	"github.com/IkBenJur/__PROJECT_SLUG__/internal/json"
	repo "github.com/IkBenJur/__PROJECT_SLUG__/internal/postgres/sqlc"
	"github.com/IkBenJur/__PROJECT_SLUG__/internal/utils"
	"github.com/gin-gonic/gin"
)

type contextKey string

const UserKey contextKey = "user"

// RequireAuth verifies the bearer token, loads the referenced user, and
// stores it in the gin context for downstream handlers to read via UserFromContext.
func RequireAuth(issuer *auth.TokenIssuer, queries repo.Querier) gin.HandlerFunc {
	return func(c *gin.Context) {
		header := c.GetHeader("Authorization")
		parts := strings.SplitN(header, " ", 2)
		if len(parts) != 2 || parts[0] != "Bearer" {
			json.WriteErrorFromString(c, http.StatusUnauthorized, "missing or malformed authorization header")
			c.Abort()
			return
		}

		claims, err := issuer.Verify(parts[1])
		if err != nil {
			json.WriteErrorFromString(c, http.StatusUnauthorized, "invalid or expired token")
			c.Abort()
			return
		}

		userID, err := utils.ParseUUID(claims.UserID)
		if err != nil {
			json.WriteErrorFromString(c, http.StatusUnauthorized, "invalid token subject")
			c.Abort()
			return
		}

		user, err := queries.FindUserById(c, userID)
		if err != nil {
			json.WriteErrorFromStringWithErrorObjectLog(c, http.StatusUnauthorized, "user not found", err)
			c.Abort()
			return
		}

		c.Set(string(UserKey), user)
		c.Next()
	}
}

func UserFromContext(c *gin.Context) (repo.User, bool) {
	val, exists := c.Get(string(UserKey))
	if !exists {
		return repo.User{}, false
	}
	user, ok := val.(repo.User)
	return user, ok
}
