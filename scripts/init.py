#!/usr/bin/env python3
"""
Initialize this template as a new project.

Usage: python3 scripts/init.py "My Project"

Run from inside a clone/fork of this repo (not the template repo itself).
Replaces placeholder tokens, installs backend and frontend dependencies,
verifies the result builds, and sets up a local git repo.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PLACEHOLDER_NAME = "__PROJECT_NAME__"
PLACEHOLDER_SLUG = "__PROJECT_SLUG__"

# Files containing placeholder tokens to replace.
FILES = [
    "README.md",
    "backend/go.mod",
    "backend/docker-compose.yaml",
    "backend/.env.example",
    "backend/cmd/main.go",
    "backend/cmd/api.go",
    "backend/internal/middleware/auth.go",
    "backend/internal/users/handler.go",
    "frontend/package.json",
    "frontend/app/routes/home.tsx",
    "frontend/app/routes/login.tsx",
    "frontend/app/components/Header.tsx",
]


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    if not slug:
        raise ValueError(f"project name {name!r} has no usable characters for a slug")
    return slug


def run(cmd: list[str], cwd: Path) -> None:
    print(f"  $ {' '.join(cmd)}   (in {cwd.relative_to(ROOT) or '.'})")
    subprocess.run(cmd, cwd=cwd, check=True)


def replace_placeholders(name: str, slug: str) -> None:
    for rel_path in FILES:
        path = ROOT / rel_path
        text = path.read_text()
        updated = text.replace(PLACEHOLDER_NAME, name).replace(PLACEHOLDER_SLUG, slug)
        if updated != text:
            path.write_text(updated)
            print(f"  updated {rel_path}")


def install_backend() -> None:
    backend = ROOT / "backend"
    run(["go", "mod", "download"], backend)
    run(["go", "build", "./..."], backend)


def install_frontend() -> None:
    frontend = ROOT / "frontend"
    run(["npm", "install"], frontend)
    run(["npm", "run", "typecheck"], frontend)


def init_git() -> None:
    if (ROOT / ".git").exists():
        print("  git repo already exists, skipping")
        return

    try:
        subprocess.run(["gh", "auth", "status"], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("  gh not authenticated (run `gh auth login`), skipping git init")
        return

    run(["git", "init"], ROOT)
    run(["git", "add", "-A"], ROOT)
    run(["git", "commit", "-m", "Initial commit"], ROOT)
    print(
        "\n  Local git repo created. To push it to GitHub:\n"
        "    git remote add origin <your-repo-url>\n"
        "    git push -u origin main"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_name", help="Human-readable project name, e.g. 'My Project'")
    args = parser.parse_args()

    name = args.project_name.strip()
    if not name:
        sys.exit("project_name must not be empty")
    slug = slugify(name)

    print(f"Initializing '{name}' (slug: {slug})\n")

    print("[1/4] Replacing placeholders...")
    replace_placeholders(name, slug)

    print("\n[2/4] Installing backend dependencies...")
    install_backend()

    print("\n[3/4] Installing frontend dependencies...")
    install_frontend()

    print("\n[4/4] Setting up git...")
    init_git()

    print("\nDone.")


if __name__ == "__main__":
    main()
