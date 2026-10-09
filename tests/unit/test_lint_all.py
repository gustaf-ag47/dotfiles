"""The local aggregate lint gate must not silently skip CI's StyLua gate."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class LintAllTests(unittest.TestCase):
    def test_all_fails_without_stylua_and_runs_it_when_present(self):
        with tempfile.TemporaryDirectory() as directory:
            tools = Path(directory)
            for name in ('dirname', 'find', 'head', 'grep'):
                (tools / name).symlink_to(shutil.which(name))
            for name in ('shellcheck', 'luacheck', 'yamllint'):
                executable = tools / name
                executable.write_text('#!/bin/sh\nexit 0\n')
                executable.chmod(0o755)
            env = dict(os.environ, PATH=directory, LINT_USE_LOCAL='1')
            command = ['/bin/bash', str(ROOT / 'bin/lint'), '--all']
            missing = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn('stylua not installed', missing.stdout)

            stylua = tools / 'stylua'
            stylua.write_text('#!/bin/sh\n[ "$1" = "--check" ]\n')
            stylua.chmod(0o755)
            present = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
            self.assertEqual(present.returncode, 0, present.stdout + present.stderr)
            self.assertIn('All linters complete', present.stdout)
