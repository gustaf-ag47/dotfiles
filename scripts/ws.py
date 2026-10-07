import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ws_yaml  # noqa: E402

DEFAULT_WORKSPACE_YAML = Path(
    os.environ.get("WORKSPACE_YAML")
    or (Path(os.environ.get("LOCAL_CONFIG", str(Path.home() / "sync/dotfiles-local"))) / "workspace/workspace.yaml")
)

REQUIRED_ENV = ["SYNC", "NOTES", "DOTFILES", "SRC", "WORKTREES"]


def load_workspace(path):
    if not path.exists():
        raise SystemExit(f"ws: workspace file not found: {path}")
    doc = ws_yaml.load_path(path)
    doc.setdefault("env", {})
    doc.setdefault("areas", [])
    doc.setdefault("projects", [])
    doc.setdefault("repos", [])
    doc.setdefault("sessions", [])
    doc.setdefault("units", [])
    return doc


def find_by_name(items, name):
    for item in items:
        if item.get("name") == name:
            return item
    return None


def resolve_route(doc, target):
    project = find_by_name(doc["projects"], target)
    area_name = project["area"] if project else target
    area = find_by_name(doc["areas"], area_name)
    if area is None:
        return None
    session = (project or {}).get("session") or area.get("session")
    cwd = (project or {}).get("cwd") or area.get("cwd")
    runs = (project or {}).get("runs") or area.get("runs")
    window_prefix = (project or {}).get("window_prefix") or area.get("window_prefix") or "sub-"
    if not session or not cwd:
        return None
    return {
        "session": session,
        "window_prefix": window_prefix,
        "cwd": cwd,
        "runs": runs or "",
    }


def cmd_route(args):
    doc = load_workspace(Path(args.workspace))
    route = resolve_route(doc, args.target)
    if route is None:
        print(f"ws: no route for {args.target!r}", file=sys.stderr)
        return 1
    print(f"{route['session']} {route['window_prefix']} {route['cwd']} {route['runs']}")
    return 0


def tmux(args, check=False):
    try:
        result = subprocess.run(
            ["tmux", *args], capture_output=True, text=True, check=check
        )
    except FileNotFoundError:
        return subprocess.CompletedProcess(args, 1, "", "tmux not found")
    return result


def tmux_sessions():
    result = tmux(["list-sessions", "-F", "#{session_name}"])
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line]


def tmux_windows():
    result = tmux(["list-windows", "-a", "-F", "#{session_name}:#{window_name}"])
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line]


def git_status_line(repo_path):
    path = Path(repo_path)
    if not (path / ".git").exists() and not path.exists():
        return None
    try:
        porcelain = subprocess.run(
            ["git", "-C", str(path), "status", "--porcelain"],
            capture_output=True, text=True, check=True,
        ).stdout
        dirty = bool(porcelain.strip())
        ahead_behind = subprocess.run(
            ["git", "-C", str(path), "rev-list", "--left-right", "--count", "HEAD...@{u}"],
            capture_output=True, text=True,
        )
        ahead, behind = "?", "?"
        if ahead_behind.returncode == 0:
            parts = ahead_behind.stdout.split()
            if len(parts) == 2:
                ahead, behind = parts
        return {"dirty": dirty, "ahead": ahead, "behind": behind}
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def git_worktrees_under(repo_paths, tmp_root="/tmp"):
    """Real git worktrees (per `git worktree list --porcelain`) whose path
    is under tmp_root, across the given repos. A directory that merely
    matches the naming convention but that git doesn't know about (a log
    file, a leftover scratch dir, ...) is not a worktree and must not be
    reported here -- see stray_tmp_dirs.
    """
    tmp_root = str(tmp_root).rstrip("/") or "/"
    found = []
    seen_repos = set()
    for repo_path in repo_paths:
        repo_path = str(repo_path)
        if repo_path in seen_repos or not Path(repo_path).exists():
            continue
        seen_repos.add(repo_path)
        result = subprocess.run(
            ["git", "-C", repo_path, "worktree", "list", "--porcelain"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            continue
        for line in result.stdout.splitlines():
            if not line.startswith("worktree "):
                continue
            wt_path = line[len("worktree "):].strip()
            if wt_path == tmp_root or wt_path.startswith(tmp_root + "/"):
                if wt_path not in found:
                    found.append(wt_path)
    return found


def stray_tmp_dirs(known_worktrees, tmp_root="/tmp"):
    """wt-* directories under tmp_root that git doesn't report as a
    worktree for any of the checked repos -- informational only, never a
    reason to fail ws check.
    """
    known = set(known_worktrees)
    found = []
    p = Path(tmp_root)
    if not p.exists():
        return found
    for entry in sorted(p.glob("wt-*")):
        if entry.is_dir() and str(entry) not in known:
            found.append(str(entry))
    return found


def find_pane_ids_in_cron_prompts(notes_dir):
    import re

    pattern = re.compile(r"%\d{3,}")
    hits = []
    jobs = Path(os.environ.get("HOME", "")) / ".hermes/cron/jobs.json"
    if jobs.exists():
        text = jobs.read_text(errors="ignore")
        if pattern.search(text):
            hits.append(str(jobs))
    return hits


def lane_manifest_dirs(doc):
    dirs = []
    for area in doc["areas"]:
        runs = area.get("runs")
        if runs:
            dirs.append(Path(runs) / ".lanes")
    return dirs


def open_lanes(doc):
    lanes = []
    for lane_dir in lane_manifest_dirs(doc):
        if not lane_dir.exists():
            continue
        for manifest_path in sorted(lane_dir.glob("*.json")):
            try:
                manifest = json.loads(manifest_path.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            if manifest.get("status") == "closed":
                continue
            manifest["_path"] = str(manifest_path)
            lanes.append(manifest)
    return lanes


def cmd_check(args):
    doc = load_workspace(Path(args.workspace))
    lines = []
    ok = True

    missing_env = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing_env:
        ok = False
        lines.append(f"env: MISSING {', '.join(missing_env)}")
    else:
        lines.append("env: ok (" + ", ".join(f"{n}={os.environ[n]}" for n in REQUIRED_ENV) + ")")

    sessions = set(tmux_sessions())
    declared_sessions = {area["session"] for area in doc["areas"] if area.get("session")}
    missing_sessions = sorted(declared_sessions - sessions)
    if missing_sessions:
        lines.append(f"sessions: missing {', '.join(missing_sessions)}")
    else:
        lines.append(f"sessions: all {len(declared_sessions)} declared sessions are open")

    windows = tmux_windows()
    unmanaged_sessions = sorted(sessions - declared_sessions)
    if unmanaged_sessions:
        lines.append(f"sessions: unmanaged (not in workspace.yaml) {', '.join(unmanaged_sessions)}")

    repo_lines = []
    for repo in doc["repos"]:
        status = git_status_line(repo["path"])
        if status is None:
            repo_lines.append(f"  {repo['path']}: not checked out")
            continue
        flags = []
        if status["dirty"]:
            flags.append("dirty")
        if status["ahead"] not in ("0", "?"):
            flags.append(f"ahead {status['ahead']}")
        if status["behind"] not in ("0", "?"):
            flags.append(f"behind {status['behind']}")
        if flags:
            repo_lines.append(f"  {repo['path']}: {', '.join(flags)}")
    lines.append(f"repos: {len(doc['repos'])} declared" + (f"\n" + "\n".join(repo_lines) if repo_lines else ", all clean/in sync"))

    repo_paths = [repo["path"] for repo in doc["repos"] if repo.get("path")]
    tmp_worktrees = git_worktrees_under(repo_paths)
    if tmp_worktrees:
        ok = False
        lines.append(f"worktrees in /tmp (forbidden): {', '.join(tmp_worktrees)}")
    else:
        lines.append("worktrees in /tmp: none")
    stray = stray_tmp_dirs(tmp_worktrees)
    if stray:
        lines.append(f"stray /tmp dirs (not worktrees): {', '.join(stray)}")

    cron_hits = find_pane_ids_in_cron_prompts(doc["env"].get("NOTES", ""))
    if cron_hits:
        lines.append(f"pane ids (%NNNN) found in cron prompts: {', '.join(cron_hits)}")
    else:
        lines.append("pane ids in cron prompts: none found")

    declared_units = {u["name"] for u in doc["units"] if u.get("name")}
    missing_units = []
    for unit in declared_units:
        result = subprocess.run(
            ["systemctl", "--user", "is-enabled", unit],
            capture_output=True, text=True,
        )
        if result.returncode != 0 and "enabled" not in result.stdout:
            missing_units.append(unit)
    if missing_units:
        lines.append(f"units: not enabled {', '.join(sorted(missing_units))}")
    else:
        lines.append(f"units: all {len(declared_units)} declared units enabled")

    lanes = open_lanes(doc)
    lane_windows = {f"{l.get('session')}:{l.get('window')}" for l in lanes}
    windows_set = set(windows)
    lanes_without_window = sorted(lane_windows - windows_set)
    if lanes_without_window:
        lines.append(f"open lanes with no matching window: {', '.join(lanes_without_window)}")
    else:
        lines.append(f"open lanes: {len(lanes)}, all have a matching window")

    rissne_root = Path(doc["env"].get("SRC", "")) / "rissne"
    rissne_validators = [
        rissne_root / "scripts/validate-hardware.py",
        rissne_root / "scripts/validate-boot-dependencies.py",
    ]
    present = [v for v in rissne_validators if v.exists()]
    if present:
        failed = []
        for validator in present:
            result = subprocess.run(["python3", str(validator)], capture_output=True, text=True, cwd=str(rissne_root))
            if result.returncode != 0:
                failed.append(validator.name)
        lines.append(f"host layer (rissne validators): {'FAILED ' + ', '.join(failed) if failed else 'ok (' + ', '.join(v.name for v in present) + ')'}")
    else:
        lines.append("host layer (rissne validators): not found, skipped")

    print("\n".join(lines))
    return 0 if ok else 1


def cmd_up(args):
    doc = load_workspace(Path(args.workspace))
    actions = []

    for name in REQUIRED_ENV:
        if not os.environ.get(name):
            actions.append(f"env: {name} is not set in this shell; source config/zsh/.zshenv or re-login")

    sessions = set(tmux_sessions())
    for area in doc["areas"]:
        session = area.get("session")
        cwd = area.get("cwd")
        if not session or session in sessions:
            continue
        actions.append(f"session: create {session!r} at {cwd}")
        if not args.dry_run:
            tmux(["new-session", "-d", "-s", session, "-c", cwd or str(Path.home())])

    for unit in doc["units"]:
        unit_name = unit.get("name")
        if not unit_name:
            continue
        result = subprocess.run(
            ["systemctl", "--user", "is-enabled", unit_name], capture_output=True, text=True
        )
        if "enabled" not in result.stdout:
            actions.append(f"unit: enable {unit_name}")
            if not args.dry_run:
                subprocess.run(["systemctl", "--user", "enable", unit_name], check=False)

    lanes = open_lanes(doc)
    windows = set(tmux_windows())
    auto_lanes = [l for l in lanes if l.get("resume") == "auto" and f"{l.get('session')}:{l.get('window')}" not in windows]
    confirm_lanes = [l for l in lanes if l.get("resume") != "auto" and f"{l.get('session')}:{l.get('window')}" not in windows]

    for lane in auto_lanes:
        actions.append(f"lane: reopen (auto) {lane.get('session')}:{lane.get('window')} in {lane.get('cwd')}")
        if not args.dry_run:
            reopen_lane(lane)

    if confirm_lanes and not args.non_interactive:
        print(f"{len(confirm_lanes)} lane(s) need confirmation to reopen:")
        for lane in confirm_lanes:
            print(f"  {lane.get('session')}:{lane.get('window')} ({lane.get('cwd')})")
        answer = input("Reopen all of them? [y/N] ") if not args.dry_run else "n"
        if answer.strip().lower() == "y":
            for lane in confirm_lanes:
                actions.append(f"lane: reopen (confirmed) {lane.get('session')}:{lane.get('window')}")
                if not args.dry_run:
                    reopen_lane(lane)
    elif confirm_lanes:
        actions.append(f"lanes: {len(confirm_lanes)} lane(s) skipped (non-interactive, resume != auto)")

    if args.dry_run or not actions:
        print("\n".join(actions) if actions else "ws up: nothing to do")
    else:
        print("\n".join(actions))
    return 0


def reopen_lane(lane):
    session = lane.get("session")
    window = lane.get("window")
    cwd = lane.get("cwd")
    if not session or not window or not cwd:
        return
    tmux(["new-session", "-d", "-s", session]) if session not in tmux_sessions() else None
    tmux(["new-window", "-t", f"{session}:", "-n", window, "-c", cwd, "-d"])
    tmux(["send-keys", "-t", f"{session}:{window}", "-l", "--", "pi --continue"])
    tmux(["send-keys", "-t", f"{session}:{window}", "Enter"])


def main():
    parser = argparse.ArgumentParser(prog="ws")
    parser.add_argument("--workspace", default=str(DEFAULT_WORKSPACE_YAML))
    sub = parser.add_subparsers(dest="command", required=True)

    route_parser = sub.add_parser("route")
    route_parser.add_argument("target")
    route_parser.set_defaults(func=cmd_route)

    check_parser = sub.add_parser("check")
    check_parser.set_defaults(func=cmd_check)

    up_parser = sub.add_parser("up")
    up_parser.add_argument("--dry-run", action="store_true")
    up_parser.add_argument("--non-interactive", action="store_true")
    up_parser.set_defaults(func=cmd_up)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
