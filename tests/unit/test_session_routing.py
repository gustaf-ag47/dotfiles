"""Live recipient resolution never falls back to pane identity or a stale PID."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("routing", ROOT / "config/pi/skills/delegate/scripts/session_routing.py")
R = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(R)
SID = "11111111-1111-4111-8111-111111111111"


class RoutingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        environment = patch.dict(os.environ, PI_DELEGATE_MAILBOX=str(self.root / 'mailbox'))
        environment.start()
        self.addCleanup(environment.stop)
        self.file = self.root / "session.jsonl"
        self.file.write_text(json.dumps({"type": "session", "id": SID}) + "\nDO NOT READ TRANSCRIPT")
        self.state = self.root / "pi-panes"
        self.state.mkdir()
        self.data = dict(session_id=SID, session_file=str(self.file), pid=123,
                         pane="%8", socket="/test/socket", start_ticks="99", boot_id="boot")
        self.put()
        for pid in (123, 124):
            (self.state / f"{pid}.mailbox").write_text(json.dumps(dict(protocol=2, session_id=SID,
                start_ticks="99", boot_id="boot", mailbox=str(self.root / 'mailbox'))))

    def put(self, data=None, name="123.json"):
        (self.state / name).write_text(json.dumps(data or self.data))

    def resolve(self, output="%8\t100\t0\n", descendant=True, comm="pi"):
        original = Path.read_text
        def read(path, *args, **kwargs):
            if str(path) == "/proc/sys/kernel/random/boot_id":
                return "boot"
            if str(path).endswith("/comm"):
                return comm
            return original(path, *args, **kwargs)
        with patch.dict(os.environ, XDG_STATE_HOME=str(self.root)), \
             patch.object(R.subprocess, "check_output", side_effect=[output, "/test/socket\n"]), \
             patch.object(R, "pane_processes", return_value={123, 124} if (self.state / "124.json").exists() else {123}), \
             patch.object(R, "process_info", return_value=(100, "99")), \
             patch.object(R, "descendant", return_value=descendant), \
             patch.object(Path, "read_text", read):
            return R.live_target("%8")

    def test_full_opaque_custom_id_validation(self):
        self.assertEqual(R.session_id('fixture.session-1'), 'fixture.session-1')
        for bad in ('', '../file', 'prefix*', '-leading', 'trailing_', 'with space', 'a' * 129):
            with self.assertRaises(ValueError):
                R.session_id(bad)

    def test_live_verified_session(self):
        self.assertEqual(self.resolve()["session_id"], SID)

    def test_missing_stale_wrong_pid_wrong_header_and_shell_fail_closed(self):
        for field, value in (("pid", 9), ("start_ticks", "98"), ("boot_id", "old"),
                             ("socket", "/another/socket"), ("pane", "%9"), ("session_id", "wrong")):
            with self.subTest(field=field):
                self.put(self.data | {field: value})
                with self.assertRaises(ValueError):
                    self.resolve()
        self.put()
        for kwargs in (dict(descendant=False), dict(comm="bash"), dict(output="%8\t100\t1\n")):
            with self.assertRaises(ValueError):
                self.resolve(**kwargs)
        (self.state / "123.json").unlink()
        (self.state / "123").write_text(str(self.file))  # legacy path is not authority
        with self.assertRaises(ValueError):
            self.resolve()

    def test_old_consumer_and_stale_capability_are_refused(self):
        capability = self.state / "123.mailbox"
        for data in (dict(protocol=1), dict(protocol=2, session_id=SID, start_ticks="98", boot_id="boot")):
            capability.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                self.resolve()
        capability.unlink()
        with self.assertRaises(ValueError):
            self.resolve()

    def test_ambiguity(self):
        with self.assertRaises(ValueError):
            self.resolve(output="%8\t100\t0\n%9\t101\t0\n")
        self.put(self.data | {"pid": 124}, "124.json")
        with self.assertRaises(ValueError):
            self.resolve()

    def test_mixed_old_and_new_publishers_in_same_pane_are_ambiguous(self):
        with patch.object(R, "pane_processes", return_value={123, 124}), \
             patch.object(R.subprocess, "check_output", return_value="%8\t100\t0\n"):
            with self.assertRaisesRegex(ValueError, "no unique live Pi"):
                R.live_target("%8")  # only one has metadata; must still refuse

    def test_dead_process(self):
        with patch.dict(os.environ, XDG_STATE_HOME=str(self.root)), \
             patch.object(R.subprocess, "check_output", side_effect=["%8\t100\t0", "/test/socket"]):
            with self.assertRaises(ValueError):
                R.live_target("%8")  # pid 123 absent on ordinary test hosts or metadata mismatch

    def test_caller_header_and_id_must_match(self):
        with patch.dict(os.environ, PI_SESSION_ID=SID, PI_SESSION_FILE=str(self.file)):
            self.assertEqual(R.caller()["session_id"], SID)
        with patch.dict(os.environ, PI_SESSION_ID="wrong", PI_SESSION_FILE=str(self.file)):
            with self.assertRaises(ValueError):
                R.caller()

    def test_direct_session_send_does_not_need_tmux_or_live_target(self):
        env = os.environ | {"PI_DELEGATE_MAILBOX": str(self.root / "mailbox")}
        result = subprocess.run([str(ROOT / "bin/delegate-send"), f"session:{SID}", "--text", "literal `$(no)`"],
                                env=env, capture_output=True, text=True, check=True)
        record = Path(result.stdout.strip())
        self.assertIn(f"- recipient_session_id: `{SID}`", record.read_text())
        state = json.loads((record.parent / "state" / (record.name + ".json")).read_text())
        self.assertEqual(state["recipient_session_id"], SID)
