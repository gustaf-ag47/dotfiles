"""bin/aws: cache `eks get-token` until near expiry, pass everything else through."""

import datetime as dt
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "bin" / "aws"

FAKE = """#!/bin/bash
echo "$*" >> "$FAKE_LOG"
if [ "${FAKE_FAIL:-0}" = 1 ]; then echo boom >&2; exit 3; fi
case "$*" in
*get-token*) printf '{"kind": "ExecCredential", "status": {"expirationTimestamp": "%s", "token": "k8s-aws-v1.%s"}}\\n' "$FAKE_EXP" "$AWS_PROFILE" ;;
*) echo "real aws $*" ;;
esac
"""


class AwsShimTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.real_dir = root / "real"
        self.real_dir.mkdir()
        (self.real_dir / "aws").write_text(FAKE)
        (self.real_dir / "aws").chmod(0o755)
        self.shim_dir = root / "shim"
        self.shim_dir.mkdir()
        (self.shim_dir / "aws").symlink_to(SCRIPT)
        self.runtime = root / "run"
        self.runtime.mkdir(mode=0o700)
        self.log = root / "calls.log"

    def tearDown(self):
        self.tmp.cleanup()

    def run_aws(self, *args, minutes=14, **env_extra):
        exp = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
        env = os.environ.copy()
        env.update(
            PATH=f"{self.shim_dir}:{self.real_dir}:/usr/bin:/bin",
            XDG_RUNTIME_DIR=str(self.runtime),
            FAKE_LOG=str(self.log),
            FAKE_EXP=exp,
            AWS_PROFILE="a",
            HOME=self.tmp.name,
        )
        env.update(env_extra)
        return subprocess.run([str(self.shim_dir / "aws"), *args], text=True, capture_output=True, env=env, timeout=20)

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    TOKEN = ("--region", "eu-north-1", "eks", "get-token", "--cluster-name", "c", "--output", "json")

    def test_second_call_is_served_from_cache(self):
        first = self.run_aws(*self.TOKEN)
        second = self.run_aws(*self.TOKEN)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)
        self.assertIn("k8s-aws-v1.a", second.stdout)
        self.assertEqual(len(self.calls()), 1)
        files = [f for f in (self.runtime / "aws-eks-token").iterdir() if f.suffix == ".json"]
        self.assertEqual(oct(files[0].stat().st_mode & 0o777), "0o600")

    def test_profile_is_part_of_the_key(self):
        self.run_aws(*self.TOKEN)
        other = self.run_aws(*self.TOKEN, AWS_PROFILE="b")
        self.assertIn("k8s-aws-v1.b", other.stdout)
        self.assertEqual(len(self.calls()), 2)

    def test_near_expiry_token_is_refreshed(self):
        self.run_aws(*self.TOKEN, minutes=1)
        self.run_aws(*self.TOKEN, minutes=1)
        self.assertEqual(len(self.calls()), 2)

    def test_other_commands_pass_through(self):
        out = self.run_aws("s3", "ls")
        self.assertEqual(out.stdout.strip(), "real aws s3 ls")
        self.run_aws("s3", "ls")
        self.assertEqual(len(self.calls()), 2)

    def test_non_json_output_is_not_cached(self):
        self.run_aws("eks", "get-token", "--cluster-name", "c", "--output", "text")
        self.run_aws("eks", "get-token", "--cluster-name", "c", "--output", "text")
        self.assertEqual(len(self.calls()), 2)

    def test_failure_is_passed_on_and_not_cached(self):
        out = self.run_aws(*self.TOKEN, FAKE_FAIL="1")
        self.assertEqual(out.returncode, 3)
        self.assertIn("boom", out.stderr)
        ok = self.run_aws(*self.TOKEN)
        self.assertEqual(ok.returncode, 0)
        self.assertEqual(len(self.calls()), 2)

    def test_prefers_v2_installer_tree_over_path(self):
        v2 = Path(self.tmp.name) / ".local/aws-cli/v2/current/bin"
        v2.mkdir(parents=True)
        (v2 / "aws").write_text('#!/bin/bash\necho v2 "$*"\n')
        (v2 / "aws").chmod(0o755)
        self.assertEqual(self.run_aws("--version").stdout.strip(), "v2 --version")

    def test_bypass_env(self):
        self.run_aws(*self.TOKEN, AWS_EKS_TOKEN_CACHE="0")
        self.run_aws(*self.TOKEN, AWS_EKS_TOKEN_CACHE="0")
        self.assertEqual(len(self.calls()), 2)


if __name__ == "__main__":
    unittest.main()
