"""bin/pkgpick: selection state, file round-trip, and agreement with install-system.sh."""

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_loader = SourceFileLoader("pkgpick", str(ROOT / "bin/pkgpick"))
pkgpick = module_from_spec(spec_from_loader("pkgpick", _loader))
_loader.exec_module(pkgpick)

ROLES = {
    "base": [("git", "repo"), ("zsh", "repo")],
    "dev": [("go", "repo"), ("docker", "repo"), ("lazydocker-bin", "aur")],
    "personal": [("anki", "repo"), ("docker", "repo")],
}


class StateTest(unittest.TestCase):
    def test_deselect_and_reselect_a_role_package(self):
        st = pkgpick.State(ROLES, ["base", "dev"])
        st.toggle_pkg("go")
        self.assertFalse(st.is_on("go"))
        self.assertEqual(st.off, {"go"})
        st.toggle_pkg("go")
        self.assertTrue(st.is_on("go"))
        self.assertEqual(st.off, set())

    def test_add_from_a_disabled_role(self):
        st = pkgpick.State(ROLES, ["base"])
        st.toggle_pkg("anki")
        self.assertTrue(st.is_on("anki"))
        self.assertEqual(st.on, {"anki"})

    def test_role_toggle_normalizes_overrides(self):
        st = pkgpick.State(ROLES, ["base", "dev"])
        st.toggle_pkg("go")  # -go
        st.toggle_role("dev")  # dev off: -go is now meaningless
        self.assertEqual(st.off, set())
        st.toggle_pkg("lazydocker-bin")  # +lazydocker-bin
        st.toggle_role("dev")  # dev on again: + is redundant
        self.assertEqual(st.on, set())
        self.assertTrue(st.is_on("lazydocker-bin"))

    def test_shared_package_stays_while_any_enabled_role_brings_it(self):
        st = pkgpick.State(ROLES, ["base", "personal"])
        self.assertTrue(st.is_on("docker"))
        st.toggle_role("personal")
        self.assertFalse(st.is_on("docker"))

    def test_base_role_is_always_on(self):
        st = pkgpick.State(ROLES, ["dev"])  # profile forgot base
        self.assertIn("base", st.enabled)
        st.toggle_role("base")
        self.assertIn("base", st.enabled)
        st.toggle_pkg("zsh")  # single packages inside base can still go
        self.assertFalse(st.is_on("zsh"))

    def test_effective_is_sorted_and_deduplicated(self):
        st = pkgpick.State(ROLES, ["dev", "personal"])
        names = [p for p, _ in st.effective()]
        self.assertEqual(names, sorted(set(names)))
        self.assertEqual(names.count("docker"), 1)


class RoundTripAndInstallSystemTest(unittest.TestCase):
    """On a throwaway copy of the repo, pkgpick's effective list must match
    what install-system.sh --list would install from the role layers."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        for d in ("system", "profiles", "scripts"):
            shutil.copytree(ROOT / d, self.tmp / d)
        self.host = "xps14"
        # Fixed roles for the test, independent of what the real profile picks.
        prof = self.tmp / "profiles" / f"{self.host}.env"
        prof.write_text(re.sub(r"^PROFILE_ROLES=.*$", 'PROFILE_ROLES="base desktop dev work personal"',
                               prof.read_text(), flags=re.M))

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def install_system_list(self):
        env = dict(os.environ, DOTFILES=str(self.tmp))
        env.pop("PROFILE", None)
        out = subprocess.run(
            ["bash", str(self.tmp / "scripts/install-system.sh"), "--profile", self.host, "--list"],
            env=env, capture_output=True, text=True, check=True,
        ).stdout
        return {m.group(1) for m in re.finditer(r"^  \[[x ]\] (\S+)$", out, re.M)}, out

    def hardware(self):
        names = set()
        for sub in ("common", "gpu/intel", f"hosts/{self.host}"):
            for f in ("packages", "packages.aur"):
                names.update(pkgpick.entries(self.tmp / "system" / sub / f))
        return names

    def test_selection_round_trip_and_install_system_agree(self):
        roles = pkgpick.load_roles(self.tmp)
        st = pkgpick.State(roles, pkgpick.read_profile_roles(self.host, self.tmp))
        st.toggle_role("personal")  # drop a whole role
        dev_pkg = next(p for p, _ in roles["dev"] if st.roles_of(p) == ["dev"])  # only dev brings it
        st.toggle_pkg(dev_pkg)  # deselect one package of an enabled role
        latex_pkg = roles["latex"][0][0]
        st.toggle_pkg(latex_pkg)  # add one from a disabled role
        pkgpick.write_selection(self.host, st, self.tmp)

        enabled = pkgpick.read_profile_roles(self.host, self.tmp)
        off, on = pkgpick.read_select(self.host, self.tmp)
        self.assertNotIn("personal", enabled)
        self.assertEqual(pkgpick.State(roles, enabled, off, on).to_json(), st.to_json())

        listed, out = self.install_system_list()
        picked = {p for p, _ in st.effective()}
        self.assertTrue(picked <= listed, f"missing from install-system: {sorted(picked - listed)}")
        self.assertTrue(listed - picked <= self.hardware(),
                        f"install-system adds non-hardware: {sorted(listed - picked - self.hardware())}")
        self.assertIn(latex_pkg, listed)
        if dev_pkg not in self.hardware():
            self.assertNotIn(dev_pkg, listed)
        self.assertIn("deselected in packages.select", out)

    def test_clearing_the_selection_removes_the_file(self):
        roles = pkgpick.load_roles(self.tmp)
        st = pkgpick.State(roles, pkgpick.read_profile_roles(self.host, self.tmp))
        st.toggle_pkg(roles["base"][0][0])
        pkgpick.write_selection(self.host, st, self.tmp)
        self.assertTrue(pkgpick.select_path(self.host, self.tmp).exists())
        st.toggle_pkg(roles["base"][0][0])
        pkgpick.write_selection(self.host, st, self.tmp)
        self.assertFalse(pkgpick.select_path(self.host, self.tmp).exists())


if __name__ == "__main__":
    unittest.main()
