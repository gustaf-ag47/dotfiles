"""host-diag: secret-gist upload keeps a bounded history; no command lines."""
import importlib.util
import json
import sys
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
_loader = SourceFileLoader("host_diag", str(ROOT / "bin/host-diag"))
_spec = importlib.util.spec_from_loader("host_diag", _loader)
hd = importlib.util.module_from_spec(_spec)
_loader.exec_module(hd)


class UploadTests(unittest.TestCase):
    def _run(self, gists, files):
        calls = []

        def fake_sh(*cmd, timeout=30):
            if cmd[-1].startswith("/gists?"):
                return json.dumps(gists)
            return json.dumps({"files": {f: {} for f in files}})

        def fake_run(cmd, input=None, **kw):
            calls.append((cmd, json.loads(input)))
            return mock.Mock(returncode=0, stderr="")

        with mock.patch.object(hd, "sh", fake_sh), mock.patch.object(hd.subprocess, "run", fake_run):
            hd.upload("box", "report")
        return calls

    def test_creates_secret_gist_first_time(self):
        (cmd, body), = self._run([], [])
        self.assertIn("POST", cmd)
        self.assertFalse(body["public"])
        self.assertEqual(body["description"], "host-diag box")

    def test_appends_and_prunes_oldest(self):
        old = [f"box-2026010{i % 10}T{i:06d}.md" for i in range(hd.KEEP)]
        (cmd, body), = self._run([{"id": "g1", "description": "host-diag box"}], old)
        self.assertIn("/gists/g1", cmd)
        removed = [f for f, v in body["files"].items() if v is None]
        added = [f for f, v in body["files"].items() if v is not None]
        self.assertEqual(len(removed), 1)
        self.assertEqual(removed[0], sorted(old)[0])
        self.assertEqual(len(added), 1)

    def test_never_reads_cmdline(self):
        self.assertNotIn("cmdline", (ROOT / "bin/host-diag").read_text())


if __name__ == "__main__":
    unittest.main()
