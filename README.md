# herdr-claude-limits

A [Herdr](https://herdr.dev) app mod that shows your Claude Pro/Max
subscription usage limits in a thin strip at the bottom of the window:

```
✻ ━━──── 26% 4h 7m · ━───── 19% 6d 2h
```

![preview](preview.png)

- First the rolling 5-hour window, then the 7-day window: each as a bar,
  the percent used and the time left until it resets (`4h 7m`, `6d 2h`,
  `12m`).
- The bar and percent turn yellow from 80% and red from 95%.
- Data older than 15 minutes is dimmed and marked `· 2h ago`.
- Click the strip to re-read now; it also re-reads every 15 s.

## Requirements

- Herdr app 0.1.14 or later.
- Claude Code 2.1.80 or later, signed in with a Pro or Max plan. The
  limits appear only after the first API response of a session.
- `python3` on `PATH` (standard library only).
- Linux (tested). macOS should work but is untested.

## How it gets the numbers

Claude Code runs your `statusLine` command on every statusline update and
passes it JSON on stdin, including `rate_limits.five_hour` and
`rate_limits.seven_day` (`used_percentage`, `resets_at`). The mod ships a
small wrapper, `claude-limits-tap`, that you install as that command in
front of your existing one:

```json
"statusLine": {
  "type": "command",
  "command": "'/home/you/.config/herdr-app/mods/claude-limits/claude-limits-tap' -- ccstatusline"
}
```

On each run the tap:

1. reads stdin;
2. if it holds `rate_limits`, saves the two windows to
   `~/.local/state/herdr-claude-limits/rate_limits.json` (atomically, and
   only when they changed or the last save is a minute old);
3. replaces itself with your original command, fed the same stdin bytes,
   so your statusline prints, fails and exits exactly as before.

One argument after `--` is run as a shell string (`/bin/sh -c`); several
are run as a plain argument list. Any error while saving is ignored, so
the tap can't break your statusline. It adds about 30 ms.

The mod only reads that file. With no Claude Code session running it shows
the last captured values, dimmed once they are 15 minutes old.

## Install

```sh
cd herdr-claude-limits        # this repository
./install.sh                 # copy the mod, print the statusLine snippet
./install.sh --statusline    # also wrap your current statusLine command
```

- The mod goes to `${HERDR_APP_HOME:-~/.config/herdr-app}/mods/claude-limits`.
  An existing, different copy is replaced only with `--force`.
- `--statusline` edits `${CLAUDE_CONFIG_DIR:-~/.claude}/settings.json`:
  it saves `settings.json.bak-<time>` first, keeps every other setting
  (including `refreshInterval`), and never wraps twice. With no statusline
  configured it sets the tap alone, which prints nothing.
- **Where the strip appears:** the first time Herdr sees the mod, it docks
  the strip at the bottom of whichever layout is shown at that moment, and
  only that one. To use it in another layout, switch to that layout before
  installing, or add a block with `"content": { "mod": "claude-limits" }`
  and `"size": { "px": 26 }` to your own layout. Shipped layouts are
  read-only, so clone one first with `layout.clone`.
- New Claude Code sessions pick up the change; running ones do on their
  next settings reload.

## Uninstall

```sh
./install.sh --uninstall-statusline           # restore your original statusLine command
rm -r ~/.config/herdr-app/mods/claude-limits  # remove the mod
rm -r ~/.local/state/herdr-claude-limits      # remove the captured numbers
```

Restore the statusline **before** removing the mod: the wrapped command
points at the tap inside the mod folder.

## Privacy

No network access and no credentials. The tap and the mod never read
`~/.claude/.credentials.json`, the keychain or any token, and never call an
Anthropic endpoint. They only use what Claude Code already hands its
statusline command, and store two percentages, two reset times, the config
folder path and a timestamp in one local file.

## Tests

```sh
python3 -m unittest discover -s tests
herdr-app check mods/claude-limits
```

## License

MIT
