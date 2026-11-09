#!/usr/bin/env bash
# Install the claude-limits Herdr mod and, on request, its Claude Code statusLine tap.
#
#   ./install.sh                         copy the mod; print the statusLine snippet
#   ./install.sh --force                 overwrite an existing, different mods/claude-limits
#   ./install.sh --statusline            also wrap the statusLine command in settings.json
#   ./install.sh --uninstall-statusline  restore the original statusLine command (mod untouched)
set -euo pipefail

src="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/mods/claude-limits"
app_home="${HERDR_APP_HOME:-$HOME/.config/herdr-app}"
target="$app_home/mods/claude-limits"
tap="$target/claude-limits-tap"
settings="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/settings.json"

force=0 statusline=0 uninstall=0
for arg in "$@"; do
  case "$arg" in
    --force) force=1 ;;
    --statusline) statusline=1 ;;
    --uninstall-statusline) uninstall=1 ;;
    -h | --help) sed -n '2,8p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done
if ((statusline && uninstall)); then
  echo "--statusline and --uninstall-statusline are exclusive" >&2
  exit 2
fi

# The settings edit lives in the mod folder (claude-limits-statusline), so a
# gallery install, which copies only that folder, can run it too.
edit_settings() {
  python3 "$1/claude-limits-statusline" "$2"
}

if ((uninstall)); then
  edit_settings "$src" unwrap
  exit 0
fi

if [[ -e "$target" ]] && ! diff -rq "$src" "$target" >/dev/null 2>&1; then
  if ((!force)); then
    echo "$target exists and differs; rerun with --force to overwrite it" >&2
    exit 1
  fi
  rm -rf -- "$target"
fi
if [[ -e "$target" ]]; then
  echo "mod already installed and up to date: $target"
else
  mkdir -p "$app_home/mods"
  cp -R "$src" "$target"
  chmod +x "$tap" "$target/claude-limits-statusline"
  echo "installed mod: $target"
fi

if ((statusline)); then
  edit_settings "$target" wrap
else
  cat <<EOF

To feed it, wrap your Claude Code statusLine in $settings
(or rerun with --statusline to do it for you):

  "statusLine": { "type": "command", "command": "$tap -- <your current statusline command>" }

With no statusline of your own, use just "$tap".
EOF
fi
