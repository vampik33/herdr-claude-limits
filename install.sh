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

# Edits settings.json's statusLine.command with python (never sed): keeps every
# other key and refreshInterval, writes a timestamped backup first, never
# double-wraps. $1: wrap | unwrap.
edit_settings() {
  python3 - "$1" "$settings" "$tap" <<'PY'
import json, os, shlex, shutil, sys, time

mode, path, tap = sys.argv[1:]
try:
    with open(path, encoding="utf-8") as f:
        settings = json.load(f)
except FileNotFoundError:
    settings = {}

line = settings.get("statusLine")
command = line.get("command") if isinstance(line, dict) else None

def tap_args(cmd):
    """The args after the tap, or None when cmd isn't our tap."""
    try:
        words = shlex.split(cmd or "")
    except ValueError:
        return None
    if words and os.path.basename(words[0]) == "claude-limits-tap":
        return words[1:]
    return None

wrapped = tap_args(command)
if mode == "wrap":
    if wrapped is not None:
        print(f"statusLine already wrapped: {command}")
        sys.exit(0)
    if isinstance(line, dict) and line.get("type", "command") == "command" and command:
        line["command"] = f"{shlex.quote(tap)} -- {shlex.quote(command)}"
    elif line is None:
        settings["statusLine"] = {"type": "command", "command": shlex.quote(tap)}
    else:
        sys.exit(f"unexpected statusLine in {path}: {json.dumps(line)}")
else:
    if wrapped is None:
        print("statusLine is not wrapped by claude-limits-tap; nothing to restore")
        sys.exit(0)
    rest = wrapped[1:] if wrapped[:1] == ["--"] else []
    if not rest:
        del settings["statusLine"]  # the tap was the whole statusLine
    else:
        line["command"] = rest[0] if len(rest) == 1 else shlex.join(rest)

if os.path.exists(path):
    backup = f"{path}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(path, backup)
    print(f"backup: {backup}")
tmp = f"{path}.claude-limits.tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(settings, f, indent=2, ensure_ascii=False)
    f.write("\n")
if os.path.exists(path):
    shutil.copymode(path, tmp)
os.replace(tmp, path)
after = settings.get("statusLine", {}).get("command")
print(f"statusLine.command: {after}" if after else "statusLine removed")
PY
}

if ((uninstall)); then
  edit_settings unwrap
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
  chmod +x "$tap"
  echo "installed mod: $target"
fi

if ((statusline)); then
  mkdir -p "$(dirname "$settings")"
  edit_settings wrap
else
  cat <<EOF

To feed it, wrap your Claude Code statusLine in $settings
(or rerun with --statusline to do it for you):

  "statusLine": { "type": "command", "command": "$tap -- <your current statusline command>" }

With no statusline of your own, use just "$tap".
EOF
fi
