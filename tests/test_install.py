import glob
import json
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTALL = os.path.join(ROOT, "install.sh")

# The shape of a real settings.json: other keys around statusLine.
SETTINGS = {
    "model": "opus",
    "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "true"}]}]},
    "statusLine": {"type": "command", "command": "ccstatusline", "refreshInterval": 5},
    "language": "English",
}


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = os.path.join(self.tmp.name, "claude")
        self.app = os.path.join(self.tmp.name, "app home")  # a space, to exercise quoting
        os.makedirs(self.cfg)
        self.settings = os.path.join(self.cfg, "settings.json")
        self.write(SETTINGS)
        self.tap = os.path.join(self.app, "mods", "claude-limits", "claude-limits-tap")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, settings):
        with open(self.settings, "w") as f:
            json.dump(settings, f, indent=2)

    def read(self):
        with open(self.settings) as f:
            return json.load(f)

    def install(self, *args):
        env = dict(os.environ, CLAUDE_CONFIG_DIR=self.cfg, HERDR_APP_HOME=self.app)
        return subprocess.run(["bash", INSTALL, *args], capture_output=True, text=True, env=env, timeout=30)

    def backups(self):
        return glob.glob(self.settings + ".bak-*")

    def test_plain_install_copies_mod_and_leaves_settings(self):
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        for name in ("main.js", "mod.json", "claude-limits-tap"):
            self.assertTrue(os.path.exists(os.path.join(self.app, "mods", "claude-limits", name)))
        self.assertTrue(os.access(self.tap, os.X_OK))
        self.assertEqual(self.read(), SETTINGS)
        self.assertIn('"statusLine"', r.stdout)
        self.assertEqual(self.backups(), [])

    def test_existing_different_target_needs_force(self):
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual(self.install().returncode, 0)  # identical: fine
        with open(os.path.join(self.app, "mods", "claude-limits", "main.js"), "a") as f:
            f.write("// local edit\n")
        r = self.install()
        self.assertEqual(r.returncode, 1)
        self.assertIn("--force", r.stderr)
        self.assertEqual(self.install("--force").returncode, 0)
        with open(os.path.join(self.app, "mods", "claude-limits", "main.js")) as f:
            self.assertNotIn("local edit", f.read())

    def test_statusline_wraps_and_preserves_other_keys(self):
        r = self.install("--statusline")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.read()
        expected = dict(SETTINGS, statusLine={"type": "command", "command": f"'{self.tap}' -- ccstatusline", "refreshInterval": 5})
        self.assertEqual(s, expected)
        self.assertEqual(list(s), list(SETTINGS))  # key order kept
        self.assertEqual(len(self.backups()), 1)
        with open(self.backups()[0]) as f:
            self.assertEqual(json.load(f), SETTINGS)

    def test_statusline_is_idempotent(self):
        self.install("--statusline")
        once = self.read()
        r = self.install("--statusline")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("already wrapped", r.stdout)
        self.assertEqual(self.read(), once)
        self.assertEqual(len(self.backups()), 1)

    def test_uninstall_restores_original(self):
        self.install("--statusline")
        r = self.install("--uninstall-statusline")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.read(), SETTINGS)
        r = self.install("--uninstall-statusline")  # again: nothing to do
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("nothing to restore", r.stdout)
        self.assertEqual(self.read(), SETTINGS)

    def test_round_trip_shell_command(self):
        original = "bash ~/my line.sh | head -1 && echo \"it's\""
        self.write(dict(SETTINGS, statusLine={"type": "command", "command": original}))
        self.install("--statusline")
        wrapped = self.read()["statusLine"]["command"]
        # The wrapped command, run by a shell, hands the tap exactly the original string.
        out = subprocess.run(["sh", "-c", wrapped.replace(f"'{self.tap}'", "printf '%s\\n'")], capture_output=True, text=True)
        self.assertEqual(out.stdout.splitlines(), ["--", original])
        self.install("--uninstall-statusline")
        self.assertEqual(self.read()["statusLine"]["command"], original)

    def test_no_statusline_yet(self):
        self.write({"model": "opus"})
        self.install("--statusline")
        self.assertEqual(self.read()["statusLine"], {"type": "command", "command": f"'{self.tap}'"})
        self.install("--uninstall-statusline")
        self.assertEqual(self.read(), {"model": "opus"})


    def test_gallery_install_wraps_from_copied_folder(self):
        # A gallery install copies only mods/claude-limits/ (here under another
        # name) and runs the script inside it; the tap must be that copy's.
        folder = os.path.join(self.tmp.name, "gallery", "mods", "claude-limits-2")
        shutil.copytree(os.path.join(ROOT, "mods", "claude-limits"), folder)
        tap = os.path.join(folder, "claude-limits-tap")
        os.chmod(tap, 0o644)  # copied file by file, without +x
        env = dict(os.environ, CLAUDE_CONFIG_DIR=self.cfg)
        script = os.path.join(folder, "claude-limits-statusline")
        r = subprocess.run(["python3", script, "wrap"], capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.access(tap, os.X_OK))
        self.assertEqual(self.read()["statusLine"]["command"], f"{tap} -- ccstatusline")
        self.assertEqual(len(self.backups()), 1)
        r = subprocess.run(["python3", script, "unwrap"], capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.read(), SETTINGS)

    def symlink_settings(self):
        real = os.path.join(self.tmp.name, "dotfiles", "settings.json")
        os.makedirs(os.path.dirname(real))
        shutil.move(self.settings, real)
        os.symlink(real, self.settings)
        return real

    def test_symlinked_settings_stays_a_symlink(self):
        # settings.json managed by a dotfiles repo: edit the target, keep the link.
        real = self.symlink_settings()
        self.assertEqual(self.install("--statusline").returncode, 0)
        self.assertTrue(os.path.islink(self.settings))
        self.assertTrue(self.read()["statusLine"]["command"].startswith(f"'{self.tap}' -- "))
        self.assertEqual(len(self.backups()), 1)  # beside the link
        self.assertEqual(os.listdir(os.path.dirname(real)), ["settings.json"])  # dotfiles repo stays clean
        self.assertEqual(self.install("--uninstall-statusline").returncode, 0)
        self.assertTrue(os.path.islink(self.settings))
        self.assertEqual(self.read(), SETTINGS)

    def test_dangling_symlinked_settings_is_created_through_the_link(self):
        real = self.symlink_settings()
        os.remove(real)
        self.assertEqual(self.install("--statusline").returncode, 0)
        self.assertTrue(os.path.islink(self.settings))
        self.assertEqual(self.read()["statusLine"]["command"], f"'{self.tap}'")
        self.assertEqual(self.backups(), [])

    def test_wrap_retargets_a_missing_tap(self):
        # Wrapped by a tap that is gone (mod moved): wrap points it at this tap.
        gone = os.path.join(self.tmp.name, "old", "claude-limits-tap")
        self.write(dict(SETTINGS, statusLine={"type": "command", "command": f"{gone} -- ccstatusline", "refreshInterval": 5}))
        r = self.install("--statusline")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.read()["statusLine"]["command"], f"'{self.tap}' -- ccstatusline")
        self.assertEqual(self.install("--uninstall-statusline").returncode, 0)
        self.assertEqual(self.read(), SETTINGS)

    def test_wrap_retarget_keeps_a_quoted_command(self):
        gone = os.path.join(self.tmp.name, "old dir", "claude-limits-tap")
        for rest in (" -- 'ccstatusline --x | cat'", ' -- printf "%s" "$HOME"', " -- ccstatusline | cat", "\nprintf visible"):
            with self.subTest(rest):
                self.write(dict(SETTINGS, statusLine={"type": "command", "command": f"'{gone}'{rest}"}))
                self.assertEqual(self.install("--statusline").returncode, 0)
                self.assertEqual(self.read()["statusLine"]["command"], f"'{self.tap}'{rest}")

    def test_wrap_retargets_a_missing_tap_with_no_wrapped_command(self):
        gone = os.path.join(self.tmp.name, "old", "claude-limits-tap")
        self.write(dict(SETTINGS, statusLine={"type": "command", "command": gone}))
        self.assertEqual(self.install("--statusline").returncode, 0)
        self.assertEqual(self.read()["statusLine"]["command"], f"'{self.tap}'")

    def test_wrap_leaves_an_existing_other_tap_alone(self):
        # Another copy of the mod is still installed: already wrapped, no rewrite.
        other = os.path.join(self.tmp.name, "other", "claude-limits-tap")
        os.makedirs(os.path.dirname(other))
        shutil.copy(os.path.join(ROOT, "mods", "claude-limits", "claude-limits-tap"), other)
        settings = dict(SETTINGS, statusLine={"type": "command", "command": f"{other} -- ccstatusline"})
        self.write(settings)
        r = self.install("--statusline")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("already wrapped", r.stdout)
        self.assertEqual(self.read(), settings)
        self.assertEqual(self.backups(), [])

    def test_unwrap_restores_a_hand_written_command_verbatim(self):
        # Hand-written wrappers aren't one quoted word: the shell syntax after -- must survive.
        tap = os.path.join(self.tmp.name, "a dir", "claude-limits-tap")
        for rest in ("foo | cat", 'printf "%s" "$HOME"', "a  'b c'", "foo\nbar"):
            with self.subTest(rest):
                self.write(dict(SETTINGS, statusLine={"type": "command", "command": f"'{tap}' -- {rest}", "refreshInterval": 5}))
                r = self.install("--uninstall-statusline")
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(self.read()["statusLine"], {"type": "command", "command": rest, "refreshInterval": 5})

    def test_unwrap_decodes_a_single_quoted_command(self):
        self.write(dict(SETTINGS, statusLine={"type": "command", "command": f"'{self.tap}' -- 'foo --x | cat'"}))
        self.assertEqual(self.install("--uninstall-statusline").returncode, 0)
        self.assertEqual(self.read()["statusLine"]["command"], "foo --x | cat")

    def assert_refused(self, content, r, real):
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("cannot update settings.json", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertTrue(os.path.islink(self.settings))
        self.assertEqual(self.read(), content)
        self.assertEqual(self.backups(), [])
        self.assertEqual(os.listdir(os.path.dirname(real)), ["settings.json"])  # no temp file left

    def test_read_only_symlink_target_is_a_clear_error(self):
        # (file mode, its folder's mode): a Nix-store-like target, then each half alone.
        self.assertEqual(self.install().returncode, 0)  # the tap exists, so unwrap and wrap reach the write
        real = self.symlink_settings()
        dotfiles = os.path.dirname(real)
        wrapped = dict(SETTINGS, statusLine=dict(SETTINGS["statusLine"], command=f"'{self.tap}' -- ccstatusline"))
        for file_mode, dir_mode in ((0o444, 0o555), (0o444, 0o755), (0o644, 0o555)):
            for flag, content in (("--statusline", SETTINGS), ("--uninstall-statusline", wrapped)):
                with self.subTest(flag=flag, file_mode=oct(file_mode), dir_mode=oct(dir_mode)):
                    os.chmod(real, 0o644)
                    self.write(content)
                    os.chmod(real, file_mode)
                    os.chmod(dotfiles, dir_mode)
                    try:
                        r = self.install(flag)
                    finally:
                        os.chmod(dotfiles, 0o755)
                    self.assert_refused(content, r, real)

    def test_read_only_folder_with_a_stale_temp_file_changes_nothing(self):
        # A writable temp file from an interrupted run can be rewritten even in a read-only folder.
        real = self.symlink_settings()
        dotfiles = os.path.dirname(real)
        stale = real + ".claude-limits.tmp"
        with open(stale, "w") as f:
            f.write("stale")
        os.chmod(dotfiles, 0o555)
        try:
            r = self.install("--statusline")
        finally:
            os.chmod(dotfiles, 0o755)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("cannot update settings.json", r.stderr)
        self.assertEqual(self.read(), SETTINGS)
        self.assertEqual(self.backups(), [])
        with open(stale) as f:
            self.assertEqual(f.read(), "stale")

    def test_unwritable_backup_folder_is_a_clear_error_and_leaves_no_temp_file(self):
        real = self.symlink_settings()
        os.chmod(self.cfg, 0o555)
        try:
            r = self.install("--statusline")
        finally:
            os.chmod(self.cfg, 0o755)
        self.assert_refused(SETTINGS, r, real)

    def test_plain_read_only_settings_is_still_replaced(self):
        # Only a symlinked target is refused; a plain file keeps its old behaviour.
        os.chmod(self.settings, 0o444)
        r = self.install("--statusline")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.read()["statusLine"]["command"].startswith(f"'{self.tap}' -- "))
        self.assertEqual(os.stat(self.settings).st_mode & 0o777, 0o444)


if __name__ == "__main__":
    unittest.main()
