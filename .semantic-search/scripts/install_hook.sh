#!/usr/bin/env bash
# Install the semantic-search git hooks (post-commit and post-merge).
#
# Usage: bash .semantic-search/scripts/install_hook.sh
#
# Creates symlinks from .git/hooks/{post-commit,post-merge} to
# .semantic-search/hooks/{post-commit,post-merge}.
# Falls back to file copies on systems where symlinks are unavailable (e.g. some
# Windows configurations without Developer Mode).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"

install_hook() {
  local HOOK_NAME="$1"
  local SRC="$REPO_ROOT/.semantic-search/hooks/$HOOK_NAME"
  local DST="$REPO_ROOT/.git/hooks/$HOOK_NAME"

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
  echo "Hook '$HOOK_NAME' installed."
}

for HOOK in post-commit post-merge; do
  install_hook "$HOOK"
done

echo "All hooks installed. They will run on commits and merges to the main branch."
