# NixOS VM test: agent-git must refuse force push, force-with-lease, +refspec,
# --mirror, --prune and ref deletion, while normal push/fetch/rebase keep
# working. `pkgs` must already have overlay.nix applied.
{ pkgs }:

pkgs.testers.runNixOSTest {
  name = "agent-git-refusals";

  nodes.machine = { pkgs, ... }: {
    environment.systemPackages = [ pkgs.agent-git ];
  };

  testScript = ''
    machine.wait_for_unit("multi-user.target")

    git = "${pkgs.agent-git}/bin/git -c user.name=test -c user.email=test@example.com -c init.defaultBranch=main"

    with subtest("normal push, fetch and rebase work"):
        machine.succeed(f"{git} init --bare /srv/remote.git")
        machine.succeed(f"{git} clone /srv/remote.git /root/work")
        machine.succeed(f"cd /root/work && echo one > file && {git} add file && {git} commit -m one")
        machine.succeed(f"cd /root/work && {git} push origin HEAD:main")
        original = machine.succeed("${pkgs.agent-git}/bin/git -C /srv/remote.git rev-parse main").strip()
        machine.succeed(f"cd /root/work && echo two >> file && {git} add file && {git} commit -m two && {git} push origin HEAD:main")
        machine.succeed(f"cd /root/work && {git} fetch origin")
        machine.succeed(f"cd /root/work && git checkout -b side && echo three >> file && {git} add file && {git} commit -m three && {git} rebase main")

    with subtest("force push is refused"):
        machine.succeed(f"cd /root/work && {git} checkout main")
        machine.succeed(f"cd /root/work && echo four > file && {git} commit -a --amend -m rewritten")
        pinned = machine.succeed("${pkgs.agent-git}/bin/git -C /srv/remote.git rev-parse main").strip()
        for args in ["--force origin HEAD:main", "-f origin HEAD:main",
                     "--force-with-lease origin HEAD:main",
                     "--force-with-lease=main origin HEAD:main",
                     "origin +HEAD:main"]:
            out = machine.fail(f"cd /root/work && {git} push {args} 2>&1")
            assert "disabled and not allowed" in out, f"unexpected output for `push {args}`: {out}"
        assert machine.succeed("${pkgs.agent-git}/bin/git -C /srv/remote.git rev-parse main").strip() == pinned

    with subtest("forced refspecs from config and --mirror are rejected"):
        machine.fail(f"cd /root/work && {git} -c remote.origin.push=+HEAD:refs/heads/main push origin")
        out = machine.fail(f"cd /root/work && {git} push --mirror origin 2>&1")
        assert "disabled and not allowed" in out
        machine.fail(f"cd /root/work && {git} send-pack --force /srv/remote.git +HEAD:refs/heads/main")
        assert machine.succeed("${pkgs.agent-git}/bin/git -C /srv/remote.git rev-parse main").strip() == pinned

    with subtest("--prune is rejected"):
        out = machine.fail(f"cd /root/work && {git} push --prune origin 2>&1")
        assert "disabled and not allowed" in out

    with subtest("ref deletion on push is rejected"):
        machine.succeed(f"cd /root/work && {git} branch throwaway && {git} push origin throwaway")
        out = machine.fail(f"cd /root/work && {git} push origin --delete throwaway 2>&1")
        assert "disabled and not allowed" in out
        out = machine.fail(f"cd /root/work && {git} push origin -d throwaway 2>&1")
        assert "disabled and not allowed" in out
        out = machine.fail(f"cd /root/work && {git} push origin :throwaway 2>&1")
        assert "disabled and not allowed" in out
        assert "throwaway" in machine.succeed("${pkgs.agent-git}/bin/git -C /srv/remote.git branch").strip()

    with subtest("non-forced push of rewritten history is rejected by the remote itself"):
        out = machine.fail(f"cd /root/work && {git} push origin HEAD:main 2>&1")
        assert machine.succeed("${pkgs.agent-git}/bin/git -C /srv/remote.git rev-parse main").strip() == pinned
  '';
}
