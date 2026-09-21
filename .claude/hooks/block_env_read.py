#!/usr/bin/env python3
"""PreToolUse hook for Read: blocks reading .env files, except .env.example."""
import json
import os
import sys

ALLOWED_BASENAMES = {".env.example", "example.env"}


def is_blocked(file_path: str) -> bool:
    basename = os.path.basename(file_path)
    if basename in ALLOWED_BASENAMES:
        return False
    return basename == ".env" or basename.startswith(".env.")


def main() -> None:
    payload = json.load(sys.stdin)
    file_path = payload.get("tool_input", {}).get("file_path", "")

    if file_path and is_blocked(file_path):
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    "Reading .env files is blocked to avoid leaking secrets. "
                    "Use .env.example instead."
                ),
            }
        }))


if __name__ == "__main__":
    main()
