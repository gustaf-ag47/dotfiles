"""Tests for bin/reading (reading flow: kosync, books.json, inbox cards)."""

import hashlib
import importlib.machinery
import importlib.util
import json
import sqlite3
import tempfile
import unittest
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from _helpers import stub_http

ROOT = Path(__file__).resolve().parents[2]


def load():
    loader = importlib.machinery.SourceFileLoader("reading", str(ROOT / "bin" / "reading"))
    spec = importlib.util.spec_from_loader("reading", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


reading = load()


class PartialMD5Test(unittest.TestCase):
    # Expected values from KOReader's own util.partialMD5 body run under LuaJIT
    # (bit.lshift(1024, -2) wraps to offset 0), md5 over the sampled bytes.
    def test_matches_koreader_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = bytes((i * 7 + 3) % 251 for i in range(300000))
            big, small = Path(tmp, "big.bin"), Path(tmp, "small.bin")
            big.write_bytes(data)
            small.write_bytes(data[:1500])
            self.assertEqual(reading.partial_md5(big), "3e53b613def422b326c240820288f5ef")
            self.assertEqual(reading.partial_md5(small), "77807ae5cd2ed863098dcbe3d74d4123")


class DeviceNameTest(unittest.TestCase):
    def test_libgen_names(self):
        self.assertEqual(
            reading.parse_device_name(
                "/mnt/onboard/.kobo/Kobo/Vladimir Khorikov - Unit Testing Principles, Practices, and Patterns "
                "(2019, Manning Publications).pdf"),
            ("Vladimir Khorikov", "Unit Testing Principles, Practices, and Patterns"))
        author, title = reading.parse_device_name(
            "Joe Reis_ Matt Housley - Fundamentals of Data Engineering (2022, O'Reilly Media, Inc.) - libgen.li.epub")
        self.assertEqual(title, "Fundamentals of Data Engineering")

    def test_device_books_include_kobo_sideloads_only(self):
        self.assertTrue(reading.device_book_path(Path(".kobo/Kobo/a.pdf")))
        self.assertTrue(reading.device_book_path(Path("Books/a.pdf")))
        self.assertFalse(reading.device_book_path(Path(".adds/koreader/a.pdf")))

    def test_map_device_files_hash_then_title(self):
        index = {"books": {"aaa": {"calibre_id": 1, "title": "Code That Fits in Your Head: Heuristics", "path": "x.pdf"}}}
        report = reading.map_device_files(index, [
            ("aaa", "/mnt/onboard/x.pdf"),
            ("bbb", "/mnt/onboard/.kobo/Kobo/Mark Seemann - Code That Fits in Your Head_ Heuristics (2021, AW).epub"),
            ("ccc", "/mnt/onboard/unknown.pdf")])
        self.assertEqual(index["books"]["aaa"]["device_path"], "/mnt/onboard/x.pdf")
        self.assertEqual(index["books"]["bbb"]["calibre_id"], 1)
        self.assertEqual(index["books"]["bbb"]["match"], "title")
        self.assertTrue(report[2].startswith("none"))


class ShouldPushTest(unittest.TestCase):
    me = "ME"

    def test_no_remote_pushes(self):
        self.assertEqual(reading.should_push(57, 300, {}, self.me), "push")

    def test_same_page_skips(self):
        self.assertEqual(reading.should_push(57, 300, {"progress": "57", "device_id": "KOBO"}, self.me), "skip")

    def test_kobo_ahead_is_behind(self):
        remote = {"progress": "120", "percentage": 0.4, "device_id": "KOBO", "device": "Kobo"}
        self.assertEqual(reading.should_push(57, 300, remote, self.me), "behind")

    def test_own_device_may_move_back(self):
        remote = {"progress": "120", "percentage": 0.4, "device_id": self.me}
        self.assertEqual(reading.should_push(57, 300, remote, self.me), "push")

    def test_epub_xpointer_uses_percentage(self):
        remote = {"progress": "/body/DocFragment[12]", "percentage": 0.9, "device_id": "KOBO"}
        self.assertEqual(reading.should_push(10, 100, remote, self.me), "behind")
        self.assertEqual(reading.should_push(95, 100, remote, self.me), "push")


class FakeKosyncHandler(BaseHTTPRequestHandler):
    store = {}

    def log_message(self, *args):
        pass

    def _auth(self):
        return self.headers.get("x-auth-user") == "gustaf" and self.headers.get("x-auth-key") == "KEY"

    def _reply(self, code, body):
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if not self._auth():
            return self._reply(401, {"code": 2001})
        doc = self.path.rsplit("/", 1)[1]
        self._reply(200, self.store.get(doc, {}))

    def do_PUT(self):
        if not self._auth():
            return self._reply(401, {"code": 2001})
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        body["timestamp"] = 1
        self.store[body["document"]] = body
        self._reply(200, {"document": body["document"], "timestamp": 1})


class KosyncClientTest(unittest.TestCase):
    def test_put_then_get_and_auth_headers(self):
        FakeKosyncHandler.store = {}
        with stub_http(FakeKosyncHandler) as server:
            url = f"http://127.0.0.1:{server.server_port}"
            client = reading.Kosync({"KOSYNC_URL": "http://127.0.0.1:9", "KOSYNC_TAILNET_URL": url,
                                     "KOSYNC_USER": "gustaf", "KOSYNC_KEY": "KEY"}, timeout=1)
            self.assertEqual(client.get("doc"), {})
            client.put("doc", 57, 300)
            got = client.get("doc")
            self.assertEqual(got["progress"], "57")
            self.assertAlmostEqual(got["percentage"], 0.19)
            self.assertTrue(got["device"].startswith("zathura@"))

    def test_key_derived_from_password(self):
        c = reading.Kosync({"KOSYNC_URL": "http://x", "KOSYNC_USER": "u", "KOSYNC_PASSWORD": "pw"})
        self.assertEqual(c.key, hashlib.md5(b"pw").hexdigest())


class FakeClient:
    device_id = "ME"

    def __init__(self, remote=None):
        self.remote = remote or {}
        self.puts = []

    def get(self, doc):
        return dict(self.remote)

    def put(self, doc, page, total, device=None):
        self.puts.append((doc, page, total))
        self.remote = {"progress": str(page), "device_id": self.device_id}


class WatcherTest(unittest.TestCase):
    def setUp(self):
        self.clock = [0.0]
        self.client = FakeClient()
        self.w = reading.Watcher(self.client, debounce=20, now=lambda: self.clock[0])
        self.w.index = {"books": {"md5a": {"title": "Unit Testing", "path": "lib/u.pdf"}}}
        self.w.reload_index = lambda: None
        self.file = str(reading.SYNC / "lib/u.pdf")
        self.gotos = []
        saved = (reading.zathura_goto, reading.notify)
        reading.zathura_goto = lambda bus, page: self.gotos.append(page)
        reading.notify = lambda *a, **k: ""
        self.addCleanup(lambda: setattr(reading, "zathura_goto", saved[0]) or setattr(reading, "notify", saved[1]))

    def z(self, page):
        return [{"bus": "org.pwmt.zathura.PID-1", "file": self.file, "page": page, "total": 300}]

    def test_debounced_push_and_push_on_close(self):
        self.w.tick(self.z(1))
        self.clock[0] = 5
        self.w.tick(self.z(57))
        self.assertEqual(self.client.puts, [])
        self.clock[0] = 26
        self.w.tick(self.z(57))
        self.assertEqual(self.client.puts, [("md5a", 57, 300)])
        self.clock[0] = 27
        self.w.tick(self.z(58))
        self.w.tick([])  # closed before the debounce: final push
        self.assertEqual(self.client.puts[-1], ("md5a", 58, 300))

    def test_pull_on_open_when_kobo_ahead(self):
        self.client.remote = {"progress": "120", "percentage": 0.4, "device_id": "KOBO", "device": "Kobo"}
        self.w.tick(self.z(1))
        self.assertEqual(self.gotos, [120])

    def test_never_pushes_backwards_silently(self):
        self.w.tick(self.z(130))  # opened: zathura ahead
        self.client.remote = {"progress": "200", "percentage": 0.66, "device_id": "KOBO", "device": "Kobo"}
        self.clock[0] = 1
        self.w.tick(self.z(131))
        self.clock[0] = 30
        self.w.tick(self.z(131))
        self.w.tick([])
        self.assertEqual(self.client.puts, [])

    def test_unknown_files_are_ignored(self):
        self.w.tick([{"bus": "b", "file": "/tmp/other.pdf", "page": 3, "total": 9}])
        self.clock[0] = 100
        self.w.tick([{"bus": "b", "file": "/tmp/other.pdf", "page": 4, "total": 9}])
        self.w.tick([])
        self.assertEqual(self.client.puts, [])


def src(ids, title="Code That Fits in Your Head: Heuristics"):
    return {"key": "calibre:7", "kind": "book", "ref": "calibre:7", "title": title, "author": "Mark Seemann",
            "note": None, "device": "Kobo",
            "highlights": [{"id": i, "text": f"highlight {i} with enough text", "note": "", "page": 3,
                            "chapter": "", "date": "2026-10-01"} for i in ids]}


class IngestTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.inbox = Path(self.tmp.name, "00 Inbox")
        self.ledger = {"sources": {}}

    def tearDown(self):
        self.tmp.cleanup()

    def card(self):
        return self.inbox / "Reading - Code That Fits in Your Head.md"

    def test_one_card_then_idempotent(self):
        stats = reading.ingest([src(["a", "b"])], self.inbox, self.ledger)
        self.assertEqual(stats["new_cards"], ["Reading - Code That Fits in Your Head.md"])
        text = self.card().read_text()
        for field in ("type: capture", "author: agent", "tags: [inbox]", "source_kind: book",
                      'source_ref: "calibre:7"', "highlights: 2", "last_highlight: 2026-10-01"):
            self.assertIn(field, text)
        again = reading.ingest([src(["a", "b"])], self.inbox, self.ledger)
        self.assertEqual((again["new_cards"], again["highlights"]), ([], 0))
        self.assertEqual(self.card().read_text(), text)

    def test_append_only_keeps_human_edits(self):
        reading.ingest([src(["a"])], self.inbox, self.ledger)
        edited = self.card().read_text().replace("highlight a with enough text", "MY OWN WORDS") + "\nmy note\n"
        self.card().write_text(edited)
        reading.ingest([src(["a", "b"])], self.inbox, self.ledger)
        text = self.card().read_text()
        self.assertIn("MY OWN WORDS", text)
        self.assertIn("my note", text)
        self.assertNotIn("highlight a with enough text", text)
        self.assertIn("highlight b with enough text", text)
        self.assertIn("highlights: 2", text)
        self.assertEqual(text.count("<!-- hl:b -->"), 1)

    def test_deleted_highlight_is_not_readded(self):
        reading.ingest([src(["a", "b"])], self.inbox, self.ledger)
        text = self.card().read_text()
        start = text.index("> highlight a")
        self.card().write_text(text[:start] + text[text.index("<!-- hl:a -->") + 14:])
        reading.ingest([src(["a", "b"])], self.inbox, self.ledger)
        self.assertNotIn("hl:a ", self.card().read_text())

    def test_moved_card_is_never_written(self):
        reading.ingest([src(["a"])], self.inbox, self.ledger)
        processed = Path(self.tmp.name, "30 Knowledge", "Sources", "Processed.md")
        processed.parent.mkdir(parents=True)
        self.card().rename(processed)
        self.ledger["sources"]["calibre:7"]["card"] = str(processed)
        before = processed.read_text()
        stats = reading.ingest([src(["a", "c"])], self.inbox, self.ledger)
        self.assertEqual(processed.read_text(), before)
        self.assertEqual(stats["new_cards"], ["Reading - Code That Fits in Your Head.md"])
        self.assertNotIn("hl:a ", self.card().read_text())

    def test_title_clash_gets_suffix(self):
        self.inbox.mkdir()
        self.card().write_text("---\ntype: capture\nsource_ref: \"calibre:99\"\n---\n")
        stats = reading.ingest([src(["a"])], self.inbox, self.ledger)
        self.assertEqual(stats["new_cards"], ["Reading - Code That Fits in Your Head (2).md"])


class CardNameTest(unittest.TestCase):
    def test_subtitle_kept_only_when_main_title_is_generic(self):
        self.assertEqual(reading.card_name("Code That Fits in Your Head: Heuristics for Software Engineering"),
                         "Reading - Code That Fits in Your Head.md")
        self.assertEqual(reading.card_name("Unit Testing: Principles, Practices, and Patterns"),
                         "Reading - Unit Testing - Principles, Practices, and Patterns.md")
        self.assertEqual(reading.card_name("Refactoring"), "Reading - Refactoring.md")


class SourcesTest(unittest.TestCase):
    def test_koreader_annotation_sync_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            md5 = "0123456789abcdef0123456789abcdef"
            (folder / f"{md5}.json").write_text(json.dumps({
                "k1": {"text": "A highlight long enough", "pos0": {"x": 1}, "pos1": {"x": 2}, "pageno": 46,
                       "chapter": "Ch 3", "datetime": "2026-10-15 10:00:00", "note": "mine"},
                "k2": {"text": "deleted one here", "pos0": {"x": 1}, "deleted": True},
                "k3": {"text": "", "page": 4},
            }))
            (folder / f"{md5}.progress.json").write_text("{}")
            (folder / "ffffffffffffffffffffffffffffffff.json").write_text("{}")
            report = {"junk": [], "unmapped": [], "errors": []}
            index = {"books": {md5: {"calibre_id": 5, "title": "Book", "author": "A", "note": "30 Knowledge/Sources/Book.md"}}}
            [s] = reading.koreader_sources(folder, index, report)
            self.assertEqual(s["ref"], "calibre:5")
            self.assertEqual([h["id"] for h in s["highlights"]], [f"koreader:{md5}:k1"])
            self.assertEqual(s["highlights"][0]["page"], 46)
            self.assertEqual(report["unmapped"], ["ffffffffffffffffffffffffffffffff"])

    def test_nickel_drops_short_fragments(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp, "k.sqlite")
            db = sqlite3.connect(db_path)
            db.execute("CREATE TABLE Bookmark (BookmarkID, VolumeID, ContentID, Text, Annotation, DateCreated, "
                       "ChapterProgress, Type, Hidden)")
            db.execute("CREATE TABLE content (ContentID, ContentType, Title, Attribution)")
            vol = "file:///mnt/onboard/.kobo/Kobo/Mark Seemann - Code That Fits in Your Head (2021, AW).epub"
            ch4 = vol + "#(29)OEBPS/C05_ch04.xhtml#ch4lev3"
            db.executemany("INSERT INTO Bookmark VALUES (?,?,?,?,?,?,?,?,?)", [
                ("b1", vol, ch4, "a long enough highlight here", None, "2026-02-20T10:00:00", 0.1, "highlight", "false"),
                ("b2", vol, ch4, "you may", None, "2026-02-20T10:00:00", 0.1, "highlight", "false"),
                ("b3", vol, ch4, None, None, "2026-02-21T10:00:00", 0.244, "dogear", "false"),
            ])
            db.execute("INSERT INTO content VALUES (?, 6, 'Code That Fits in Your Head', 'Mark Seemann')", (vol,))
            db.execute("INSERT INTO content VALUES (?, 9, '4.3 Outside-in', '')", (ch4,))
            db.commit()
            db.close()
            report = {"junk": [], "unmapped": [], "errors": []}
            [s] = reading.nickel_sources(db_path, {"books": {}}, report)
            self.assertEqual([h["id"] for h in s["highlights"]], ["nickel:b1", "nickel:b3"])
            self.assertEqual(s["highlights"][1]["text"], "Bookmarked: 4.3 Outside-in (24% in)")
            self.assertEqual(reading.render_highlight(s["highlights"][1]),
                             "- Bookmarked: 4.3 Outside-in (24% in) · 2026-02-21\n<!-- hl:nickel:b3 -->\n")
            self.assertEqual(len(report["junk"]), 1)


class LiteratureNoteTest(unittest.TestCase):
    def test_render_fills_file_path_and_no_progress(self):
        template = "---\ntitle: <% tp.file.title %>\ncurrent_page: 1\n---\n\n# <% tp.file.title %>\n\n## Summary\n"
        out = reading.render_literature_note(template, "Unit Testing", {"author": "Vladimir Khorikov", "path": "library/calibre/u.pdf"})
        fm = reading.frontmatter(out)
        self.assertEqual(fm["file_path"], "library/calibre/u.pdf")
        self.assertEqual(fm["status"], "reading")
        self.assertEqual(fm["current_page"], "")
        self.assertIn("# Unit Testing\n", out)
        self.assertNotIn("<%", out)

    def test_bump_frontmatter_only_touches_counters(self):
        text = "---\ntype: capture\nhighlights: 3\nlast_highlight: 2026-01-01\n---\nbody highlights: 3\n"
        out = reading.bump_frontmatter(text, 2, "2026-10-15")
        self.assertEqual(out, "---\ntype: capture\nhighlights: 5\nlast_highlight: 2026-10-15\n---\nbody highlights: 3\n")


if __name__ == "__main__":
    unittest.main()
