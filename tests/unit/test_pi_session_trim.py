import importlib.machinery
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_loader = importlib.machinery.SourceFileLoader("pi_session_trim", str(ROOT / "bin/pi-session-trim"))
trim_mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(_loader.name, _loader))
_loader.exec_module(trim_mod)


def line(**e):
    return json.dumps(e) + "\n"


class TrimTest(unittest.TestCase):
    def session(self):
        return [
            line(type="session", version=3, id="s"),
            line(type="message", id="m1", parentId=None),
            line(type="custom", customType="wait-for", id="w1", parentId="m1", data={"op": "registered"}),
            line(type="message", id="m2", parentId="w1"),
            line(type="compaction", id="c1", parentId="m2", firstKeptEntryId="m2", summary="x" * 100),
            line(type="message", id="m3", parentId="c1"),
            line(type="message", id="m4", parentId="m3"),
            line(type="model_change", id="mc", parentId="m4"),
            line(type="compaction", id="c2", parentId="mc", firstKeptEntryId="m4", summary="y"),
            line(type="message", id="m5", parentId="c2"),
            line(type="message", id="off", parentId="m3"),  # abandoned branch
            line(type="message", id="m6", parentId="m5"),
        ]

    def test_keeps_state_and_tail_drops_rest(self):
        out = [json.loads(x) for x in trim_mod.trim(self.session())]
        self.assertEqual([e["id"] for e in out], ["s", "w1", "m4", "mc", "c2", "m5", "m6"])
        self.assertIsNone(out[1]["parentId"])
        self.assertEqual(out[2]["parentId"], "w1")  # first kept re-parented onto the state chain
        self.assertEqual(out[3]["parentId"], "m4")  # tail unchanged

    def test_no_compaction_is_untouched(self):
        lines = [line(type="session", id="s"), line(type="message", id="a", parentId=None)]
        self.assertIsNone(trim_mod.trim(lines))


if __name__ == "__main__":
    unittest.main()
