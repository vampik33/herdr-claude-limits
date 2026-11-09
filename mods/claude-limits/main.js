// Claude subscription usage limits (5-hour and weekly windows), as captured
// by claude-limits-tap from Claude Code's statusLine JSON. Reads one local
// file; no network, no credentials.
import { View, div } from "gpui-kit";
import { h_flex } from "gpui-base";
import { home, readTextFile, settings, theme } from "herdr";

const STATE = "/.local/state/herdr-claude-limits/rate_limits.json";
const WINDOWS = ["five_hour", "seven_day"];
const STALE_SECONDS = 15 * 60;
const ICON = "✻";
const ICON_COLOR = "#D97757"; // Claude orange
const METER_W = 48;
const METER_H = 6;

// Time left until a reset: "6d 2h", "4h 7m", "12m".
function remaining(seconds) {
  const m = Math.max(0, Math.floor(seconds / 60));
  const d = Math.floor(m / 1440);
  const h = Math.floor((m % 1440) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m % 60}m`;
  return `${m}m`;
}

function age(seconds) {
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
  return `${Math.floor(seconds / 86400)}d`;
}

export default class ClaudeLimits extends View {
  init(_props, cx) {
    this.data = null;
    this.read(cx);
    cx.timer.every(15000, (cx) => this.read(cx));
  }

  read(cx) {
    cx.spawn(async (cx) => {
      try {
        const text = await readTextFile(home() + STATE);
        this.data = text ? JSON.parse(text) : null;
      } catch (_e) {
        this.data = null; // a half-written or unreadable file reads as "no data yet"
      }
      cx.notify();
    });
  }

  render() {
    const t = theme();
    const size = settings().ui_font_size ?? 13;
    const now = Date.now() / 1000;
    const d = this.data;
    const live = WINDOWS.filter((key) => d?.[key] && d[key].resets_at > now);
    const stale = typeof d?.captured_at === "number" && now - d.captured_at > STALE_SECONDS;
    const tone = (c) => (stale ? t.dim : c);
    const sep = () => div().text_color(t.dim).child("·");

    const windowEl = (key) => {
      const pct = Math.max(0, Math.min(100, Math.round(d[key].used_percentage)));
      const level = tone(pct >= 95 ? t.ansi1 : pct >= 80 ? t.ansi3 : null);
      const meter = div().flex_none().w(METER_W).h(METER_H).rounded_full().bg(t.border)
        .child(div().h_full().w((METER_W * pct) / 100).rounded_full().bg(level ?? tone(t.muted)));
      return h_flex().gap(6).items_center()
        .child(meter)
        .child(div().text_color(level ?? tone(t.foreground)).child(`${pct}%`))
        .child(div().text_color(tone(t.foreground)).child(remaining(d[key].resets_at - now)));
    };

    const parts = live.flatMap((key, i) => (i === 0 ? [windowEl(key)] : [sep(), windowEl(key)]));
    return h_flex().id("claude-limits").size_full().px(14).gap(8).items_center()
      .bg(t.chrome).border_t(1).border_color(t.border)
      .text_size(size).whitespace_nowrap().cursor_pointer()
      .on_click((_e, cx) => this.read(cx))
      .child(div().flex_none().text_color(tone(ICON_COLOR)).child(ICON))
      .when(live.length === 0, (el) => el.child(div().text_color(t.dim).child("… (start a Claude Code session)")))
      .children(parts)
      .when(stale, (el) => el.child(div().text_color(t.dim).child(`· ${age(now - d.captured_at)} ago`)));
  }
}
