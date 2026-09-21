package main

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"time"

	"github.com/IkBenJur/__PROJECT_SLUG__/internal/auth"
	"github.com/IkBenJur/__PROJECT_SLUG__/internal/env"
	"github.com/IkBenJur/__PROJECT_SLUG__/internal/postgres"
	repo "github.com/IkBenJur/__PROJECT_SLUG__/internal/postgres/sqlc"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/joho/godotenv"
)

func run(ctx context.Context) error {
	ctx, cancel := signal.NotifyContext(ctx, os.Interrupt)
	defer cancel()

	godotenv.Load()

	logger := slog.New(slog.NewTextHandler(os.Stdout, nil))
	slog.SetDefault(logger)

	dsn := env.GetEnv("GOOSE_DBSTRING", "host=localhost user=postgres password=postgres dbname=__PROJECT_SLUG__ sslmode=disable")

	if err := postgres.RunMigrations(ctx, dsn); err != nil {
		slog.Error("Failed to run migrations", "error", err)
		return err
	}

	conn, err := pgxpool.New(ctx, dsn)
	if err != nil {
		slog.Error("Failed DB connections", "error", err)
		return err
	}
	defer conn.Close()

	slog.Info("Connected to DB")

	queries := repo.New(conn)

	jwtSecret := env.GetEnv("JWT_SECRET", "dev-secret-change-me")
	jwtTTL := time.Duration(env.GetEnvInt("JWT_TTL_HOURS", 24)) * time.Hour
	issuer := auth.NewTokenIssuer(jwtSecret, jwtTTL)

	port := env.GetEnv("PORT", "8080")

	api := Application{
		Port:    port,
		Queries: queries,
		Issuer:  issuer,
	}

	slog.Info("Starting server")
	if err := api.Run(ctx, api.Mount()); err != nil && err != http.ErrServerClosed {
		slog.Error("Server shutdown", "error", err)
		return err
	}
	return nil
}

func main() {
	ctx := context.Background()
	if err := run(ctx); err != nil {
		fmt.Fprintf(os.Stderr, "%s\n", err)
		os.Exit(1)
	}
}
