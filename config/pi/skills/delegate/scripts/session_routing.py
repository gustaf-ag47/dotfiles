"""Session-addressed mailbox primitives. Panes locate a live publisher, never a recipient.

Only the session header is read; no transcript, credentials or payload is used
for routing. Legacy text-only pi-panes files are intentionally not authority.
"""
import json
import os
from pathlib import Path
import re
import subprocess

# Pi IDs are strings (UUID by default; --session-id/SDK allow custom IDs).
# Require the entire opaque ID, not an abbreviation or a filesystem path.
ID = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9])?\Z")


def session_id(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError("missing or invalid full Pi session ID")
    return value


def header_id(file):
    with Path(file).open() as handle:
        header = json.loads(handle.readline(65536))
    if header.get("type") != "session":
        raise ValueError("not a Pi session header")
    return session_id(header.get("id"))


def process_info(pid):
    stat = Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()
    if stat[0] == "Z":
        raise ValueError("dead Pi process")
    return int(stat[1]), stat[19]  # ppid, kernel start ticks


def descendant(pid, ancestor):
    seen = set()
    while pid > 1 and pid not in seen:
        if pid == ancestor:
            return True
        seen.add(pid)
        pid = process_info(pid)[0]
    return False


def pane_processes(root):
    """Count even old Pi instances without sidecars: mixed-version ambiguity
    must not silently select the one that happens to publish new metadata."""
    found = set()
    for proc in Path("/proc").glob("[0-9]*"):
        try:
            pid = int(proc.name)
            if (proc / "comm").read_text().strip() == "pi" and descendant(pid, root):
                process_info(pid)  # reject zombies
                found.add(pid)
        except (OSError, ValueError):
            continue
    return found


def live_target(target):
    command = (["tmux", "display-message", "-p", "-t", target, "#{pane_id}\t#{pane_pid}\t#{pane_dead}"]
               if re.fullmatch(r"%\d+", target)
               else ["tmux", "list-panes", "-t", target, "-F", "#{pane_id}\t#{pane_pid}\t#{pane_dead}"])
    panes = subprocess.check_output(command, text=True, timeout=5).splitlines()
    if len(panes) != 1:
        raise ValueError("target must resolve to exactly one pane")
    pane, root, dead = panes[0].split("\t")
    if not re.fullmatch(r"%\d+", pane) or dead != "0":
        raise ValueError("target pane is dead or invalid")
    instances = pane_processes(int(root))
    if len(instances) != 1:
        raise ValueError("target has no unique live Pi process (including old/non-publishing instances)")
    socket = subprocess.check_output(["tmux", "display-message", "-p", "-t", pane, "#{socket_path}"], text=True, timeout=5).strip()
    base = Path(os.getenv("XDG_STATE_HOME", Path.home() / ".local/state")) / "pi-panes"
    boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    matches = []
    for file in base.glob("*.json"):
        try:
            data = json.loads(file.read_text())
            pid = data["pid"]
            if pid not in instances or file.stem != str(pid) or data["pane"] != pane or data["socket"] != socket or data["boot_id"] != boot:
                continue
            if process_info(pid)[1] != data["start_ticks"] or not descendant(pid, int(root)):
                continue
            if Path(f"/proc/{pid}/comm").read_text().strip() != "pi":
                continue
            sid = session_id(data["session_id"])
            if header_id(data["session_file"]) != sid:
                continue
            capability = json.loads((base / f"{pid}.mailbox").read_text())
            if (capability.get("protocol") != 2 or capability.get("session_id") != sid
                    or capability.get("start_ticks") != data["start_ticks"] or capability.get("boot_id") != boot
                    or Path(capability.get("mailbox", "")).resolve() != Path(os.getenv(
                        "PI_DELEGATE_MAILBOX", Path.home() / ".pi/agent/delegate-mailbox")).resolve()):
                continue
            matches.append(dict(session_id=sid, session_file=data["session_file"], pane=pane, pid=pid))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    if len(matches) != 1:
        raise ValueError("no unique verified live Pi session for target; reload that agent's ID publisher AND protocol-2 mailbox consumer, and use the same PI_DELEGATE_MAILBOX (no pane fallback)")
    return matches[0]


def caller():
    sid = session_id(os.getenv("PI_SESSION_ID"))
    file = os.environ.get("PI_SESSION_FILE", "")
    if not file or header_id(file) != sid:
        raise ValueError("caller needs matching PI_SESSION_ID and PI_SESSION_FILE from a Pi shell tool")
    return dict(session_id=sid, session_file=file)


def recipient(lane):
    # Missing IDs stay unaddressed: never infer the parent from today's old pane.
    try:
        return session_id(lane.get("parent_session_id"))
    except ValueError:
        return ""
