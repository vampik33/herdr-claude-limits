import json
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAP = os.path.join(ROOT, "mods", "claude-limits", "claude-limits-tap")
# A wrapped statusline that echoes its stdin and exits 3.
FAKE = "cat; echo fake-stderr >&2; exit 3"


def payload(**windows):
    return json.dumps({"model": {"display_name": "Opus"}, "rate_limits": windows}).encode()


class TapTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.state = os.path.join(self.home.name, ".local", "state", "herdr-claude-limits", "rate_limits.json")
        self.now = int(time.time())

    def tearDown(self):
        state_dir = os.path.dirname(os.path.dirname(self.state))
        if os.path.isdir(state_dir):
            os.chmod(state_dir, stat.S_IRWXU)
        self.home.cleanup()

    def run_tap(self, data, *cmd, env=None, python_args=()):
        args = [sys.executable, *python_args, TAP] + (["--", *cmd] if cmd else [])
        e = {"HOME": self.home.name, "PATH": os.environ["PATH"]}
        e.update(env or {})
        return subprocess.run(args, input=data, capture_output=True, env=e, timeout=10)

    def read_state(self):
        with open(self.state) as f:
            return json.load(f)

    def snapshot(self):
        with open(self.state) as f:
            return os.stat(self.state).st_mtime_ns, f.read()

    def write_state(self, state):
        os.makedirs(os.path.dirname(self.state), exist_ok=True)
        with open(self.state, "w") as f:
            json.dump(state, f)

    def test_full_rate_limits(self):
        data = payload(
            five_hour={"used_percentage": 35.4, "resets_at": self.now + 3600},
            seven_day={"used_percentage": 12, "resets_at": self.now + 86400},
        )
        r = self.run_tap(data, env={"CLAUDE_CONFIG_DIR": "/cfg"})
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, b"")
        s = self.read_state()
        self.assertEqual(s["five_hour"], {"used_percentage": 35.4, "resets_at": self.now + 3600})
        self.assertEqual(s["seven_day"], {"used_percentage": 12, "resets_at": self.now + 86400})
        self.assertEqual(s["claude_config_dir"], "/cfg")
        self.assertLessEqual(abs(s["captured_at"] - self.now), 5)

    def test_default_config_dir(self):
        self.run_tap(payload(five_hour={"used_percentage": 1, "resets_at": self.now + 60}))
        self.assertEqual(self.read_state()["claude_config_dir"], os.path.join(self.home.name, ".claude"))

    def test_without_rate_limits_leaves_file_untouched(self):
        self.write_state({"five_hour": {"used_percentage": 50, "resets_at": self.now + 60}, "captured_at": 1})
        before = self.snapshot()
        r = self.run_tap(json.dumps({"model": {"display_name": "Opus"}}).encode())
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.snapshot(), before)

    def test_missing_window_keeps_unexpired_previous(self):
        old_week = {"used_percentage": 20, "resets_at": self.now + 3600}
        self.write_state({"seven_day": old_week, "claude_config_dir": os.path.join(self.home.name, ".claude"), "captured_at": self.now - 10})
        self.run_tap(payload(five_hour={"used_percentage": 5, "resets_at": self.now + 600}))
        s = self.read_state()
        self.assertEqual(s["seven_day"], old_week)
        self.assertEqual(s["five_hour"]["used_percentage"], 5)

    def test_missing_window_not_inherited_from_other_account(self):
        old_week = {"used_percentage": 98, "resets_at": self.now + 3600}
        self.write_state({"seven_day": old_week, "claude_config_dir": "/account-a", "captured_at": self.now - 10})
        self.run_tap(payload(five_hour={"used_percentage": 5, "resets_at": self.now + 600}), env={"CLAUDE_CONFIG_DIR": "/account-b"})
        s = self.read_state()
        self.assertNotIn("seven_day", s)
        self.assertEqual(s["claude_config_dir"], "/account-b")
        self.assertEqual(s["five_hour"]["used_percentage"], 5)

    def test_missing_window_drops_expired_previous(self):
        self.write_state({"seven_day": {"used_percentage": 20, "resets_at": self.now - 1}, "captured_at": self.now - 10})
        self.run_tap(payload(five_hour={"used_percentage": 5, "resets_at": self.now + 600}))
        self.assertNotIn("seven_day", self.read_state())

    def test_unchanged_values_are_not_rewritten(self):
        data = payload(five_hour={"used_percentage": 5, "resets_at": self.now + 600})
        self.run_tap(data)
        first = os.stat(self.state).st_mtime_ns
        time.sleep(0.05)
        self.run_tap(data)
        self.assertEqual(os.stat(self.state).st_mtime_ns, first)

    def test_unchanged_values_refresh_old_capture_time(self):
        w = {"used_percentage": 5, "resets_at": self.now + 600}
        self.write_state({"five_hour": w, "claude_config_dir": os.path.join(self.home.name, ".claude"), "captured_at": self.now - 3600})
        self.run_tap(payload(five_hour=w))
        self.assertGreaterEqual(self.read_state()["captured_at"], self.now)

    def test_non_json_stdin(self):
        r = self.run_tap(b"not json \xff", "sh", "-c", FAKE)
        self.assertEqual(r.returncode, 3)
        self.assertEqual(r.stdout, b"not json \xff")
        self.assertFalse(os.path.exists(self.state))

    def test_wrapped_command_gets_identical_stdin(self):
        data = payload(five_hour={"used_percentage": 99.6, "resets_at": self.now + 60}) + b"\n\x00tail"
        r = self.run_tap(data, FAKE)  # one argument: a shell string
        self.assertEqual(r.returncode, 3)
        self.assertEqual(r.stdout, data)
        self.assertEqual(r.stderr, b"fake-stderr\n")

    def test_stdin_without_memfd_create(self):
        # The macOS path: no os.memfd_create, so stdin goes through a temp file.
        runner = "import os, runpy, sys; del os.memfd_create; sys.argv = sys.argv[1:]; runpy.run_path(sys.argv[0], run_name='__main__')"
        data = payload(five_hour={"used_percentage": 7, "resets_at": self.now + 60})
        r = self.run_tap(data, FAKE, python_args=("-c", runner))
        self.assertEqual((r.returncode, r.stdout, r.stderr), (3, data, b"fake-stderr\n"))

    def test_wrapped_argv_form(self):
        data = payload(five_hour={"used_percentage": 1, "resets_at": self.now + 60})
        r = self.run_tap(data, "sh", "-c", FAKE)
        self.assertEqual((r.returncode, r.stdout), (3, data))
        self.assertTrue(os.path.exists(self.state))

    def test_large_stdin_passes_through(self):
        data = json.dumps({"rate_limits": {}, "pad": "x" * 300_000}).encode()
        r = self.run_tap(data, FAKE)
        self.assertEqual((r.returncode, r.stdout), (3, data))

    def test_no_wrapped_command(self):
        r = self.run_tap(payload(five_hour={"used_percentage": 1, "resets_at": self.now + 60}))
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, b"", b""))

    def test_missing_wrapped_program(self):
        r = self.run_tap(b"{}", "/nonexistent/statusline", "x")
        self.assertEqual(r.returncode, 127)

    def test_unwritable_state_dir_still_runs_statusline(self):
        state_dir = os.path.dirname(os.path.dirname(self.state))  # ~/.local/state
        os.makedirs(state_dir)
        os.chmod(state_dir, stat.S_IRUSR | stat.S_IXUSR)
        data = payload(five_hour={"used_percentage": 1, "resets_at": self.now + 60})
        r = self.run_tap(data, FAKE)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (3, data, b"fake-stderr\n"))
        self.assertFalse(os.path.exists(self.state))


if __name__ == "__main__":
    unittest.main()
