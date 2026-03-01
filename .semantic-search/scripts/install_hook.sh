#!/usr/bin/env bash
# Install the semantic-search post-commit hook.
#
# Usage: bash .semantic-search/scripts/install_hook.sh
#
# Creates a symlink from .git/hooks/post-commit to .semantic-search/hooks/post-commit.
# Falls back to a file copy on systems where symlinks are unavailable (e.g. some
# Windows configurations without Developer Mode).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"

SRC="$REPO_ROOT/.semantic-search/hooks/post-commit"
DST="$REPO_ROOT/.git/hooks/post-commit"

if [ ! -f "$SRC" ]; then
  echo "Error: hook source not found at $SRC" >&2
  exit 1
fi

if [ -e "$DST" ] && [ ! -L "$DST" ]; then
  echo "Warning: $DST already exists and is not a symlink."
  echo "Backing it up to $DST.bak"
  mv "$DST" "$DST.bak"
fi

if ln -sf "$SRC" "$DST" 2>/dev/null; then
  echo "Symlinked: $SRC -> $DST"
else
  cp "$SRC" "$DST"
  echo "Copied (symlink unavailable): $SRC -> $DST"
fi

chmod +x "$DST"
echo "Hook installed. It will run on every commit to the main branch."
