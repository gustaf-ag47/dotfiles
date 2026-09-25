import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('pi_setup', Path(__file__).resolve().parents[2] / 'scripts/pi_setup.py')
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)


class AdoptionTests(unittest.TestCase):
    def test_adoption_keeps_runtime_and_supports_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill = root / 'agent/skills/example'
            skill.mkdir(parents=True)
            (skill / '.venv').mkdir()
            (skill / '.venv/state').write_text('keep')
            target = skill / 'SKILL.md'
            target.write_text('old')
            auth = root / 'agent/auth.json'
            auth.write_text('private-untouched')
            source = root / 'source.md'
            source.write_text('new')
            state = root / 'state'
            operations = [('link', source, target)]
            setup.apply(operations, state)
            self.assertTrue(target.is_symlink())
            self.assertEqual(target.read_text(), 'new')
            self.assertEqual(auth.read_text(), 'private-untouched')
            self.assertEqual((skill / '.venv/state').read_text(), 'keep')
            setup.apply(operations, state)
            manifests = list(state.glob('adoption-*/manifest.json'))
            self.assertEqual(len(manifests), 1)
            setup.rollback(manifests[0])
            self.assertFalse(target.is_symlink())
            self.assertEqual(target.read_text(), 'old')

    def test_rollback_preserves_new_user_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target = root / 'source', root / 'target'
            source.write_text('new')
            target.write_text('old')
            setup.apply([('link', source, target)], root / 'state')
            target.unlink()
            target.write_text('user edit after adoption')
            with self.assertRaises(ValueError):
                setup.rollback(next((root / 'state').glob('*/manifest.json')))
            self.assertEqual(target.read_text(), 'user edit after adoption')

    def test_source_enumeration_excludes_dependencies_and_keeps_siblings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '_excalidraw').mkdir()
            (root / '_excalidraw/canvas.mjs').write_text('source')
            (root / '.venv').mkdir()
            (root / '.venv/secret').write_text('exclude')
            self.assertEqual(list(setup.source_files(root)), [root / '_excalidraw/canvas.mjs'])


if __name__ == '__main__':
    unittest.main()
