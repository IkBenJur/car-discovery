package main

import (
	"context"
	"fmt"
	"net/http"

	"github.com/IkBenJur/__PROJECT_SLUG__/internal/auth"
	"github.com/IkBenJur/__PROJECT_SLUG__/internal/middleware"
	repo "github.com/IkBenJur/__PROJECT_SLUG__/internal/postgres/sqlc"
	"github.com/IkBenJur/__PROJECT_SLUG__/internal/users"
	"github.com/gin-gonic/gin"
)

type Application struct {
	Port    string
	Queries repo.Querier
	Issuer  *auth.TokenIssuer
}

func (app *Application) Mount() http.Handler {
	router := gin.Default()

	router.Use(func(c *gin.Context) {
		c.Header("Access-Control-Allow-Origin", "*")
		c.Header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
		c.Header("Access-Control-Allow-Headers", "Content-Type, Authorization")
		if c.Request.Method == http.MethodOptions {
			c.AbortWithStatus(http.StatusNoContent)
			return
		}
		c.Next()
	})

	router.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{
			"message": "OK",
		})
	})

	userHandler := users.NewHandler(app.Queries, app.Issuer)
	router.POST("/auth/register", userHandler.Register)
	router.POST("/auth/login", userHandler.Login)

	authorized := router.Group("/", middleware.RequireAuth(app.Issuer, app.Queries))
	authorized.GET("users/me", userHandler.Me)

	return router
}

func (app *Application) Run(ctx context.Context, router http.Handler) error {
	srv := &http.Server{
		Addr:    fmt.Sprintf(":%s", app.Port),
		Handler: router,
	}

	go func() {
		<-ctx.Done()
		srv.Shutdown(context.Background())
	}()

	return srv.ListenAndServe()
}
