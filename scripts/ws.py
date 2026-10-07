import argparse
import datetime
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
    # Includes the .unrouted-lanes fallback delegate.sh and runs_dir_for_session
    # both write to for sessions with no declared area: without this, a manifest
    # written there is invisible to open_lanes, so ws adopt re-adopts the same
    # pane on every run and ws check's "open lanes" undercounts.
    dirs = []
    for area in doc["areas"]:
        runs = area.get("runs")
        if runs:
            dirs.append(Path(runs) / ".lanes")
    # No os.environ fallback here, unlike runs_dir_for_session: a doc built
    # without an "env" section (as plain dicts in tests do) means "NOTES is
    # not known", not "ask the process environment", so callers stay isolated
    # from whatever happens to be exported in this shell.
    notes = doc.get("env", {}).get("NOTES", "")
    if notes:
        unrouted = Path(notes) / ".unrouted-lanes" / ".lanes"
        if unrouted not in dirs:
            dirs.append(unrouted)
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


def area_for_session(doc, session):
    for area in doc["areas"]:
        if area.get("session") == session:
            return area
    return None


def runs_dir_for_session(doc, session):
    area = area_for_session(doc, session)
    if area and area.get("runs"):
        return area["runs"]
    route = resolve_route(doc, session.lower()) if session else None
    if route and route.get("runs"):
        return route["runs"]
    notes = doc["env"].get("NOTES") or os.environ.get("NOTES", "")
    if notes:
        return str(Path(notes) / ".unrouted-lanes")
    return ".unrouted-lanes"


AGENT_PANE_SKIP_WINDOWS = {"orchestrator", "hermes"}


def tmux_agent_panes():
    result = tmux(
        [
            "list-panes",
            "-a",
            "-F",
            "#{session_name}\t#{window_name}\t#{pane_pid}\t#{pane_current_command}\t#{pane_current_path}",
        ]
    )
    if result.returncode != 0:
        return []
    panes = []
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 5:
            continue
        session, window, pane_pid, command, cwd = parts
        panes.append(
            {
                "session": session,
                "window": window,
                "pane_pid": pane_pid,
                "command": command,
                "cwd": cwd,
            }
        )
    return panes


def unmatched_agent_panes(doc, session_filter=None, panes=None, lanes=None):
    lanes = open_lanes(doc) if lanes is None else lanes
    lane_windows = {f"{lane.get('session')}:{lane.get('window')}" for lane in lanes}
    panes = tmux_agent_panes() if panes is None else panes
    result = []
    for pane in panes:
        if pane["command"] != "pi":
            continue
        if pane["window"].lower() in AGENT_PANE_SKIP_WINDOWS:
            continue
        if session_filter and pane["session"] != session_filter:
            continue
        key = f"{pane['session']}:{pane['window']}"
        if key in lane_windows:
            continue
        result.append(pane)
    return result


def git_branch_for(cwd):
    result = subprocess.run(
        ["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    branch = result.stdout.strip()
    return branch or None


def pi_session_file_for_cwd(cwd, sessions_root=None):
    root = Path(sessions_root) if sessions_root else Path.home() / ".pi/agent/sessions"
    normalized = str(cwd).rstrip("/").lstrip("/")
    session_dir = root / f"--{normalized.replace('/', '-')}--"
    if not session_dir.is_dir():
        return None
    files = sorted(session_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return str(files[0]) if files else None


def find_pi_pid(pane_pid, ps_text=None):
    if ps_text is None:
        result = subprocess.run(["ps", "-eo", "pid,ppid,comm"], capture_output=True, text=True)
        if result.returncode != 0:
            return None
        ps_text = result.stdout
    children = {}
    comms = {}
    for line in ps_text.splitlines()[1:]:
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        pid, ppid, comm = parts
        children.setdefault(ppid, []).append(pid)
        comms[pid] = comm
    stack = [str(pane_pid)]
    seen = set()
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        if comms.get(current) == "pi":
            return current
        stack.extend(children.get(current, []))
    return None


def find_pi_env_var(pid, var, proc_root="/proc"):
    if not pid:
        return None
    path = Path(proc_root) / str(pid) / "environ"
    try:
        data = path.read_bytes()
    except OSError:
        return None
    prefix = f"{var}=".encode()
    for item in data.split(b"\x00"):
        if item.startswith(prefix):
            return item[len(prefix):].decode(errors="replace")
    return None


def build_adopt_manifest(doc, pane, proc_root="/proc", sessions_root=None, ps_text=None):
    pi_pid = find_pi_pid(pane["pane_pid"], ps_text=ps_text)
    parent = find_pi_env_var(pi_pid, "PI_DELEGATE_PARENT", proc_root=proc_root)
    run_id = (
        "adopted-"
        + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + f"-{pane['pane_pid']}"
    )
    runs = runs_dir_for_session(doc, pane["session"])
    manifest = {
        "run_id": run_id,
        "session": pane["session"],
        "window": pane["window"],
        "cwd": pane["cwd"],
        "branch": git_branch_for(pane["cwd"]),
        "pi_session": pi_session_file_for_cwd(pane["cwd"], sessions_root=sessions_root),
        "parent": parent,
        "resume": "confirm",
        "status": "open",
        "adopted": True,
        "created_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return runs, run_id, manifest


def cmd_adopt(args):
    doc = load_workspace(Path(args.workspace))
    panes = unmatched_agent_panes(doc, session_filter=args.session)
    plan = [build_adopt_manifest(doc, pane) for pane in panes]
    if not plan:
        print("ws adopt: nothing to adopt")
        return 0
    for runs, run_id, manifest in plan:
        lane_path = Path(runs) / ".lanes" / f"{run_id}.json"
        if args.dry_run:
            print(f"would adopt {manifest['session']}:{manifest['window']} -> {lane_path}")
            continue
        lane_path.parent.mkdir(parents=True, exist_ok=True)
        lane_path.write_text(json.dumps(manifest, indent=2) + "\n")
        print(f"adopted {manifest['session']}:{manifest['window']} -> {lane_path}")
    return 0


def looks_like_raw_tmux_target(session):
    return bool(session) and session[0] == "$" and session[1:].isdigit()


def resolve_tmux_session_name(raw_target):
    result = tmux(["display-message", "-p", "-t", f"{raw_target}:", "#{session_name}"])
    if result.returncode != 0:
        return None
    name = result.stdout.strip()
    return name or None


def cmd_lane_fix(args):
    doc = load_workspace(Path(args.workspace))
    dirs = lane_manifest_dirs(doc)
    windows = set(tmux_windows())
    actions = []
    seen_dirs = set()
    for lane_dir in dirs:
        if str(lane_dir) in seen_dirs or not lane_dir.exists():
            continue
        seen_dirs.add(str(lane_dir))
        for manifest_path in sorted(lane_dir.glob("*.json")):
            try:
                manifest = json.loads(manifest_path.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            if manifest.get("status") == "closed":
                continue
            session = manifest.get("session", "")
            if not looks_like_raw_tmux_target(session):
                continue
            resolved = resolve_tmux_session_name(session)
            if resolved is None:
                continue
            manifest["session"] = resolved
            window_key = f"{resolved}:{manifest.get('window')}"
            if window_key in windows:
                target_runs = runs_dir_for_session(doc, resolved)
                target_path = Path(target_runs) / ".lanes" / manifest_path.name
                actions.append(f"fix: {manifest_path} -> session={resolved}, move to {target_path}")
                if not args.dry_run:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    target_path.write_text(json.dumps(manifest, indent=2) + "\n")
                    if target_path != manifest_path:
                        manifest_path.unlink()
            else:
                manifest["status"] = "closed"
                actions.append(f"fix: {manifest_path} -> session={resolved}, window gone, closing")
                if not args.dry_run:
                    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    if not actions:
        print("ws lane fix: nothing to fix")
    else:
        print("\n".join(actions))
    return 0


def bus_unreachable(result):
    if result.returncode == 0:
        return False
    stderr = result.stderr or ""
    # systemd's actual wording varies by failure mode: "Failed to connect to
    # bus: No such file or directory" with no XDG_RUNTIME_DIR at all, but
    # "Failed to connect to user scope bus via local transport: ... not
    # defined" when neither XDG_RUNTIME_DIR nor DBUS_SESSION_BUS_ADDRESS is
    # set (the env -i case this retry exists for). Matching only the first
    # left every stripped-env ws check reporting real units as "not enabled".
    return "Failed to connect to" in stderr and "bus" in stderr


def runtime_bus_env():
    env = dict(os.environ)
    uid = os.getuid()
    env["XDG_RUNTIME_DIR"] = env.get("XDG_RUNTIME_DIR") or f"/run/user/{uid}"
    env["DBUS_SESSION_BUS_ADDRESS"] = env.get("DBUS_SESSION_BUS_ADDRESS") or f"unix:path=/run/user/{uid}/bus"
    return env


def check_declared_units(declared_units):
    missing = []
    bus_env = None
    unreachable = False
    for unit in sorted(declared_units):
        result = subprocess.run(["systemctl", "--user", "is-enabled", unit], capture_output=True, text=True)
        if bus_unreachable(result):
            if bus_env is None:
                bus_env = runtime_bus_env()
            result = subprocess.run(
                ["systemctl", "--user", "is-enabled", unit], capture_output=True, text=True, env=bus_env
            )
            if bus_unreachable(result):
                unreachable = True
                continue
        if result.returncode != 0 and "enabled" not in result.stdout:
            missing.append(unit)
    if unreachable:
        return "unknown", missing
    if missing:
        return "not_enabled", missing
    return "ok", missing


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
    unit_status, missing_units = check_declared_units(declared_units)
    if unit_status == "unknown":
        lines.append("units: unknown (no user systemd bus)")
    elif unit_status == "not_enabled":
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

    unadopted = unmatched_agent_panes(doc, lanes=lanes)
    lines.append(f"agent panes without a lane manifest: {len(unadopted)}")

    homelab_root = Path(doc["env"].get("SRC", "")) / "homelab"
    homelab_validators = [
        homelab_root / "scripts/validate-hardware.py",
        homelab_root / "scripts/validate-boot-dependencies.py",
        homelab_root / "scripts/check-live-drift.sh",
    ]
    present = [v for v in homelab_validators if v.exists()]
    if present:
        failed = []
        for validator in present:
            runner = ["bash", str(validator)] if validator.suffix == ".sh" else ["python3", str(validator)]
            result = subprocess.run(runner, capture_output=True, text=True, cwd=str(homelab_root))
            if result.returncode != 0:
                failed.append(validator.name)
        lines.append(f"host layer (homelab validators): {'FAILED ' + ', '.join(failed) if failed else 'ok (' + ', '.join(v.name for v in present) + ')'}")
    else:
        lines.append("host layer (homelab validators): not found, skipped")

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

    adopt_parser = sub.add_parser("adopt")
    adopt_parser.add_argument("--dry-run", action="store_true")
    adopt_parser.add_argument("--session")
    adopt_parser.set_defaults(func=cmd_adopt)

    lane_parser = sub.add_parser("lane")
    lane_sub = lane_parser.add_subparsers(dest="lane_command", required=True)
    lane_fix_parser = lane_sub.add_parser("fix")
    lane_fix_parser.add_argument("--dry-run", action="store_true")
    lane_fix_parser.set_defaults(func=cmd_lane_fix)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
