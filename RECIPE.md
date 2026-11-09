# Claude limits

A thin strip along the bottom of the Herdr window that shows how much of
your Claude Pro/Max subscription you have used: the 5-hour window and the
weekly window, each as a bar, a percent and the time left until it
resets. The numbers come from the JSON Claude Code hands its statusLine
command, captured by a small wrapper script; nothing is fetched.

![Claude limits](preview.png)

## What you see

- One full-width row, 26px tall, docked at the bottom (`place: "bottom"`),
  background `chrome`, a 1px `border` line on top, 14px side padding.
- Text in the app's UI font at the UI text size (`settings().ui_font_size`,
  falling back to 13px).
- Left to right, 8px apart: a `✻` in Claude orange (`#D97757`); then each
  window that has not reset yet (5-hour first, then weekly), separated by
  a `·` in `dim`. A window is, 6px apart: a 48×6px pill bar (track
  `border`, fill `muted` for the percent used), the percent (`26%`) and
  the time left until it resets (`4h 7m`; `6d 2h` from a day; `12m` under
  an hour), both in `foreground`.
  Example: `✻ ━━──── 26% 4h 7m · ━───── 19% 6d 2h`.
- Bar fill and percent are `ansi3` (yellow) from 80%, `ansi1` (red) from
  95%. The percent is rounded.
- With no data file, or no window left: `✻ … (start a Claude Code session)`
  in `dim`.

## How it behaves

- Agent statuses (working, blocked, done, idle) don't change it: it shows
  account limits, not agents.
- It re-reads the data file every 15 s. A window whose `resets_at` has
  passed disappears.
- When the data is older than 15 minutes (`captured_at`), every part turns
  `dim` and `· 2h ago` is appended (`45m`, `2h`, `3d`).
- Clicking anywhere on the strip re-reads the file at once.
- No keys, no hover effects, nothing animates.

## Built from

- `mods/claude-limits/main.js`: one `View`. `init` reads the file and starts
  `cx.timer.every(15000, …)`; `read` runs `readTextFile(home() + "/.local/state/herdr-claude-limits/rate_limits.json")`
  inside `cx.spawn`, `JSON.parse`s it (a parse error counts as no data) and
  `cx.notify()`s. `render` uses `theme()`, `settings()`, `h_flex` from
  `gpui-base` and `div` from `gpui-kit`. No `exec`, no commands, no
  shipped mods.
- `mods/claude-limits/mod.json`: `{ "place": "bottom", "size": 26, "title": "Claude limits" }`.
- `mods/claude-limits/claude-limits-tap`: Python 3, standard library only.
  It is the user's Claude Code `statusLine` command, wrapping their real one:
  `<tap> -- ccstatusline`. It reads all of stdin; if it is JSON with a
  `rate_limits` object, it merges `five_hour` and `seven_day`
  (`used_percentage`, `resets_at`) into the data file (a window absent from
  the payload keeps its old value only while its `resets_at` is in the
  future and the old file has the same `claude_config_dir`), adds `claude_config_dir` (`$CLAUDE_CONFIG_DIR` or `~/.claude`)
  and `captured_at` (Unix seconds), and writes atomically (temp file +
  `os.replace`). It skips the write when nothing changed and the last
  capture is under 60 s old. Then it puts the same stdin bytes on fd 0 (a
  `memfd`) and `execvp`s the wrapped command: one argument runs as
  `/bin/sh -c <arg>`, several run as argv. No wrapped command: no output,
  exit 0. Any error while saving is swallowed.
- `install.sh`: copies the mod into `${HERDR_APP_HOME:-~/.config/herdr-app}/mods/`
  (refuses to replace a different copy without `--force`).
  `--statusline` rewrites `statusLine.command` in
  `${CLAUDE_CONFIG_DIR:-~/.claude}/settings.json` to
  `'<tap path>' -- '<old command>'` with Python's `json`, after a
  `settings.json.bak-<time>` backup, keeping every other key and
  `refreshInterval`; it never wraps twice. `--uninstall-statusline` puts
  the old command back. Without `--statusline` it prints the snippet.

## Watch out

- The data exists only for Pro/Max subscribers, only after a session's
  first API response, and only while a Claude Code session runs (Claude Code
  2.1.80+). Between sessions the strip shows the last capture, dimmed once
  it is 15 minutes old.
- Never read `~/.claude/.credentials.json`, the keychain or a token, and
  never call an Anthropic endpoint: the statusLine JSON is the only source.
- The tap runs on every statusline update (debounced at 300 ms, and Claude
  Code cancels slow runs), so it must stay fast and must never print or
  fail on its own. Exec-ing the wrapped command keeps its output, exit code
  and cancellation exactly as before.
- A rewrite only on change would freeze `captured_at` while limits sit
  still, and the strip would call a live session stale; hence the 60 s
  refresh.
- The statusLine command points at the tap inside the installed mod folder;
  removing the mod without `--uninstall-statusline` breaks the statusline.
- Herdr docks the 26px strip only once, the first time it sees the mod
  folder, into whichever layout is shown at that moment, at the bottom of
  its root. Other layouts don't get it. To have it elsewhere, switch to that
  layout before installing, or add a `{ "type": "block", "size": { "px": 26 },
  "content": { "mod": "claude-limits" } }` node to your own layout. Shipped
  layouts are read-only, so clone one first.
- One data file per user: several `CLAUDE_CONFIG_DIR` accounts overwrite
  each other (the last one wins; `claude_config_dir` says which).

## Done when

- `herdr-app check mods/claude-limits` passes.
- `python3 -m unittest discover -s tests` passes (tap merging, expiry,
  non-JSON input, identical stdin to the wrapped command with its stdout,
  stderr and exit code, unwritable state dir; installer wrap, idempotency,
  restore, key preservation).
- `<tap> -- ccstatusline < payload.json` prints byte-for-byte what
  `ccstatusline < payload.json` prints, and writes the data file.
- With a fresh data file the strip shows both windows; at 83% the 5h bar
  is yellow, at 97% red; with `captured_at` 2 h old it is dim with
  `· 2h ago`; with no file it shows the start-a-session hint.
