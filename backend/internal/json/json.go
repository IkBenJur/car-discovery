package json

import (
	stdjson "encoding/json"
	"log/slog"
	"net/http"

	"github.com/gin-gonic/gin"
)

func WriteError(c *gin.Context, status int, error error) {
	WriteErrorFromString(c, status, error.Error())
}

func WriteErrorFromString(c *gin.Context, status int, error string) {
	slog.Error(error)
	c.JSON(status, gin.H{"error": error})
}

// Want to have proper error in log but don't send message to client
func WriteErrorFromStringWithErrorObjectLog(c *gin.Context, status int, errorString string, error error) {
	slog.Error(error.Error())
	c.JSON(status, gin.H{"error": errorString})
}

func WriteSucces(c *gin.Context, status int, message string) {
	c.JSON(status, gin.H{"message": message})
}

func WriteJSON(c *gin.Context, status int, data any) {
	c.Header("Content-Type", "application/json; charset=utf-8")
	c.Status(status)
	enc := stdjson.NewEncoder(c.Writer)
	enc.SetEscapeHTML(false)
	if err := enc.Encode(data); err != nil {
		c.Status(http.StatusInternalServerError)
	}
}
