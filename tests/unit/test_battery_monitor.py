"""battery-monitor: never hibernate on a machine without a resume device."""

from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / "bin" / "battery-monitor"


def emergency_action(resume_value):
    with tempfile.TemporaryDirectory() as temp:
        resume = Path(temp) / "resume"
        if resume_value is not None:
            resume.write_text(resume_value + "\n")
        run = subprocess.run(
            ["bash", "-c", f'source "{SCRIPT}"; emergency_action'],
            text=True, capture_output=True, timeout=10,
            env={"PATH": "/usr/bin:/bin", "HOME": temp, "POWER_RESUME_FILE": str(resume)},
        )
        assert run.returncode == 0, run.stderr
        return run.stdout.strip()


class BatteryMonitorTest(unittest.TestCase):
    def test_no_resume_device_suspends(self):
        self.assertEqual(emergency_action("0:0"), "suspend")

    def test_missing_resume_file_suspends(self):
        self.assertEqual(emergency_action(None), "suspend")

    def test_resume_device_hibernates(self):
        self.assertEqual(emergency_action("259:3"), "hibernate")


if __name__ == "__main__":
    unittest.main()
