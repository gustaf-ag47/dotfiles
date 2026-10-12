#!/usr/bin/env python3
"""One timer-driven scanner for new delegated lanes; legacy watchers retain ownership."""
import datetime as dt
import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HOME = Path.home()
BUSY = re.compile(r"[⠀-⣿] Working|Working\.\.\.|esc to interrupt")
RESULT = re.compile(r"^\s*[^\s<>][^<>]*: (PASS|BLOCKER|DONE|FAILED) ([a-fA-F0-9]{7,40}|none) - ([^\s<>]+)(?:\s+ci:\d+)?(?:\s+pr:\d+)?\s*$", re.MULTILINE)
CI = re.compile(r"ci_wait registered|CI watch registered|waiting on CI", re.IGNORECASE)
SCRIPT_DIR = Path(__file__).resolve().parent


def now():
    return int(time.time())


def run(*cmd):
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)


def capture(target, history=False):
    args = ["tmux", "capture-pane", "-J", "-p", "-t", target]
    if history:
        args += ["-S", "-400"]
    return run(*args).stdout


def window_exists(lane):
    window_id = lane.get("window_id", "")
    if not re.fullmatch(r"@\d+", window_id):
        return False
    result = run("tmux", "display-message", "-p", "-t", window_id, "#{window_id} #{session_name}:#{window_name}")
    return result.stdout.strip() == f"{window_id} {lane['session']}:{lane['window']}"


def send(target, message):
    run("tmux", "send-keys", "-t", target, "C-u")
    run("tmux", "send-keys", "-t", target, "-l", "--", message)
    run("tmux", "send-keys", "-t", target, "Enter")


def watchdog(path, target, parent):
    tool = SCRIPT_DIR.parents[4] / "bin/delegate-watchdog"
    return tool.is_file() and run(str(tool), str(path), target, parent).returncode == 10


def save(path, data):
    fd, tmp = tempfile.mkstemp(prefix=".manifest-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as out:
            json.dump(data, out, indent=2)
            out.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def created(lane):
    try:
        return int(dt.datetime.fromisoformat(lane["created_at"].replace("Z", "+00:00")).timestamp())
    except (ValueError, KeyError):
        return now()


def parent_exists(parent):
    if not parent or parent == "unknown":
        return False
    if parent.startswith("%"):
        return parent in run("tmux", "list-panes", "-a", "-F", "#{pane_id}").stdout.splitlines()
    return parent in run("tmux", "list-panes", "-a", "-F", "#{session_name}:#{window_name}").stdout.splitlines()


def finish(lane, path, state, mailbox, verdict, pane, timestamp):
    history = capture(f"{lane['session']}:{lane['window']}", True) if verdict != "window-gone" else pane
    matches = list(RESULT.finditer(history))
    match = matches[-1] if matches else None
    line = match.group().strip() if match else ""
    status = match.group(1) if match else verdict
    stamp = dt.datetime.fromtimestamp(timestamp, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rec = mailbox / f"{stamp.replace(':', '-')}_{lane['run_id']}.md"
    parent = lane.get("parent_pane") or lane.get("parent", "unknown")
    cost = (re.findall(r"\$\d+\.\d+", pane) or ["unknown"])[-1]
    tail = "\n".join(line for line in pane.splitlines() if line.strip() and not line.startswith("─"))[-3000:]
    content = (f"# Delegation {'waiting on CI' if verdict == 'waiting-on-ci' else 'finished'}: {lane.get('task') or lane['run_id']}\n\n"
               f"- window: `{lane['session']}:{lane['window']}`\n- parent: `{parent}`\n"
               f"- parent-window: `{lane.get('parent', 'unknown')}`\n- run id: `{lane['run_id']}`\n"
               f"- cwd: `{lane.get('cwd', '')}`\n- verdict: **{verdict}**\n- cost: {cost}\n- at: {stamp}\n")
    if line:
        content += f"\n## Result\n{line}\n"
    cwd = Path(lane.get("cwd") or "/nonexistent")
    reaper = cwd / "scripts/reap-finished-work.sh"
    if reaper.is_file():
        try:
            output = subprocess.run(["bash", str(reaper), "--dry-run"], capture_output=True, text=True, timeout=90, check=False).stdout
        except subprocess.TimeoutExpired:
            output = "reaper unavailable"
        content += f"\n## Finished-work dry-run\n```\n{output}\n```\n"
    content += f"\n## Last output\n```\n{tail}\n```\n"
    rec.write_text(content)
    lane.update(status="closed", result=line or None, result_status=status,
                result_sha=match.group(2) if match else None,
                result_path=match.group(3) if match else None,
                finished_at=stamp, cost=cost, mailbox_record=str(rec))
    save(path, lane)
    state.update(record=str(rec), verdict=verdict, cost=cost, nudges=0, next_nudge=timestamp)


def tick(lane, path, state, mailbox, timestamp):
    record = state.get("record")
    if record:
        rec = Path(record)
        if not rec.exists() or (mailbox / "ack" / rec.name).exists():
            if lane.get("status") == "open":
                state.pop("record", None)
            else:
                return
        max_nudges = int(os.getenv("PI_DELEGATE_MAX_NUDGES", "8"))
        if state.get("record") and (state.get("nudges", 0) >= max_nudges or timestamp < state.get("next_nudge", 0)) and lane.get("status") != "open":
            return
        parent = lane.get("parent_pane") or lane.get("parent", "unknown")
        if state.get("record") and not parent_exists(parent) and lane.get("status") != "open":
            return
        if state.get("record") and parent_exists(parent) and BUSY.search(capture(parent)) and timestamp < state.get("busy_until", timestamp + int(os.getenv("PI_DELEGATE_RENUDGE_SECS", "300"))):
            state.setdefault("busy_until", timestamp + int(os.getenv("PI_DELEGATE_RENUDGE_SECS", "300")))
            state["next_nudge"] = timestamp + 15
            if lane.get("status") != "open":
                return
        if state.get("record") and parent_exists(parent) and timestamp >= state.get("next_nudge", 0) and state.get("nudges", 0) < max_nudges:
            attempt = state.get("nudges", 0) + 1
            label = "WAITING ON CI" if state["verdict"] == "waiting-on-ci" else "FINISHED"
            message = (f"DELEGATION {label} (nudge {attempt}/{max_nudges}) — {lane.get('task') or lane['run_id']} "
                       f"in window {lane['session']}:{lane['window']} is now {state['verdict']} (cost {state['cost']}). "
                       f"Full record: {rec}. Read the record, decide what to do next, then ACKNOWLEDGE with: "
                       f"mv '{rec}' '{mailbox}/ack/' — unacknowledged records are re-nudged.")
            with (mailbox / ".nudge.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                if rec.exists():
                    send(parent, message)
            state["nudges"] = attempt
            state["next_nudge"] = timestamp + int(os.getenv("PI_DELEGATE_RENUDGE_SECS", "300"))
        if lane.get("status") != "open":
            return

    if lane.get("status") != "open" or lane.get("watcher") != "supervisor":
        return
    start = created(lane)
    if timestamp < state.get("next_poll", 0):
        return
    interval = int(os.getenv("PI_DELEGATE_POLL_SECS", "60" if timestamp - start >= 600 else "20"))
    state["next_poll"] = timestamp + interval
    target = f"{lane['session']}:{lane['window']}"
    if not window_exists(lane):
        finish(lane, path, state, mailbox, "window-gone", "", timestamp)
        return
    pane = capture(target)
    result = bool(RESULT.search(capture(target, True)))
    if not result and watchdog(path, target, lane.get("parent_pane") or lane.get("parent", "unknown")):
        state["streak"] = 0
        return
    if BUSY.search(pane):
        state["seen_busy"] = True
        state["streak"] = 0
    else:
        state["streak"] = state.get("streak", 0) + 1
        gauge = re.findall(r"\d+\.\d+%/", pane)
        started = state.get("seen_busy") or bool(gauge and gauge[-1] != "0.0%/")
        grace = int(os.getenv("PI_DELEGATE_MIN_GRACE_SECS", "45"))
        if state["streak"] >= int(os.getenv("PI_DELEGATE_IDLE_STREAK", "3")) and timestamp - start >= grace and started:
            if CI.search(pane) and not result:
                # A registered ci_wait has no final result yet. Do not close/reap it.
                if not state.get("ci_notified"):
                    state["ci_notified"] = True
                    # CI is transient; emit a single informational record without closing the lane.
                    rec = mailbox / f"{lane['run_id']}-waiting-ci.md"
                    rec.write_text(f"# Delegation waiting on CI: {lane.get('task') or lane['run_id']}\n\n- parent: `{lane.get('parent_pane') or lane.get('parent')}`\n- window: `{target}`\n- verdict: **waiting on CI**\n")
                    state.update(record=str(rec), verdict="waiting-on-ci", cost="unknown", nudges=0, next_nudge=timestamp)
                return
            if state.get("record") and state.get("verdict") == "waiting-on-ci":
                state.pop("record", None)
            if lane.get("goal") and not state.get("goal_sent") and not result:
                state["goal_sent"] = True
                send(target, lane["goal"])
                state["streak"] = 0
                return
            finish(lane, path, state, mailbox, "idle", pane, timestamp)
            return
        if timestamp - start >= grace * 4 and not started:
            finish(lane, path, state, mailbox, "never-started (prompt dropped - child has NO task)", pane, timestamp)
            return
    if timestamp - start >= int(os.getenv("PI_DELEGATE_WATCH_HOURS", "12")) * 3600:
        finish(lane, path, state, mailbox, "watch-timeout", pane, timestamp)


def scan(registry, mailbox):
    mailbox.mkdir(parents=True, exist_ok=True)
    (mailbox / "ack").mkdir(exist_ok=True)
    state_dir = mailbox / "supervisor"
    state_dir.mkdir(exist_ok=True)
    with (state_dir / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        timestamp = now()
        for link in sorted(registry.glob("*.json")):
            try:
                path = link.resolve(strict=True)
                lane = json.loads(path.read_text())
                if lane.get("watcher") != "supervisor":
                    continue
                state_path = state_dir / (lane["run_id"] + ".json")
                state = json.loads(state_path.read_text()) if state_path.exists() else {}
                tick(lane, path, state, mailbox, timestamp)
                save(state_path, state)
            except (OSError, ValueError, KeyError) as exc:
                print(f"supervisor: {link}: {exc}", file=sys.stderr)


if __name__ == "__main__":
    scan(Path(os.getenv("PI_DELEGATE_REGISTRY", HOME / ".pi/agent/delegate-lanes")),
         Path(os.getenv("PI_DELEGATE_MAILBOX", HOME / ".pi/agent/delegate-mailbox")))
