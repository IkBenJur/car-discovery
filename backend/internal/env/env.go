package env

import (
	"fmt"
	"log/slog"
	"os"
	"strconv"
)

func GetEnvOrErr(key string) (string, error) {
	if value, ok := os.LookupEnv(key); ok {
		return value, nil
	}

	slog.Error("Env variable not found", "key", key)
	return "", fmt.Errorf("failed to get key")
}

func GetEnv(key, defaultValue string) string {
	if value, ok := os.LookupEnv(key); ok {
		return value
	}
	slog.Warn("Env variable not found, resolving to default", "key", key, "default", defaultValue)
	return defaultValue
}

func GetEnvInt(key string, defaultValue int) int {
	if value, ok := os.LookupEnv(key); ok {
		if parsed, err := strconv.Atoi(value); err == nil {
			return parsed
		}
	}
	slog.Warn("Env variable not found, resolving to default", "key", key, "default", defaultValue)
	return defaultValue
}

func GetEnvBool(key string, defaultValue bool) bool {
	if value, ok := os.LookupEnv(key); ok {
		if parsed, err := strconv.ParseBool(value); err == nil {
			return parsed
		}
	}
	slog.Warn("Env variable not found, resolving to default", "key", key, "default", defaultValue)
	return defaultValue
}
