#!/bin/bash
# watch-child.sh — legacy per-child monitor. Writes a durable completion to
# PI_DELEGATE_MAILBOX addressed ONLY to the launch-time parent_session_id in the
# lane manifest. No parent/child keystroke fallback: panes may host other chats.
# Old manifests produce unaddressed records preserved by consumer quarantine.
# usage: watch-child.sh <session:window> <parent-window> <run-id> <cwd> [task] [lane-manifest]
set -uo pipefail

TARGET="${1:?target window}"
PARENT="${2:?parent window}"
RUN_ID="${3:?run id}"
CHILD_CWD="${4:-}"
TASK="${5:-}"
LANE_MANIFEST="${6:-}"

# Workspace-as-code: this watcher is the reaper for the lane manifest ws up
# reopens on login. Mark it closed on every terminal verdict, best-effort, and
# record what the child actually reported so Hermes' cron (ws lanes
# --finished-since) can read a result without re-scraping tmux history.
close_lane_manifest() {
	[ -n "$LANE_MANIFEST" ] && [ -f "$LANE_MANIFEST" ] || return 0
	command -v python3 >/dev/null 2>&1 || return 0
	# <<- strips only LEADING TABS, and strips every one of them from every
	# line, so python's own indentation below is built from spaces, not tabs
	# (see delegate.sh, which hit this first).
	python3 - "$LANE_MANIFEST" "$1" "$2" "$3" "$4" "$5" "$6" "$7" <<-'PY' 2>/dev/null || true
		import json, os, sys, tempfile
		path, result, status, sha, result_path, finished_at, cost, mailbox_record = sys.argv[1:9]
		manifest = json.load(open(path, encoding="utf-8"))
		manifest["status"] = "closed"
		manifest["result"] = result or None
		manifest["result_status"] = status or None
		manifest["result_sha"] = sha or None
		manifest["result_path"] = result_path or None
		manifest["finished_at"] = finished_at or None
		manifest["cost"] = cost or None
		manifest["mailbox_record"] = mailbox_record or None
		dir_name = os.path.dirname(path) or "."
		fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix=".manifest-", suffix=".tmp")
		os.write(fd, (json.dumps(manifest, indent=2) + "\n").encode("utf-8"))
		os.close(fd)
		os.replace(tmp_path, path)
	PY
}

MAILBOX="${PI_DELEGATE_MAILBOX:-$HOME/.pi/agent/delegate-mailbox}"
POLL_SECS="${PI_DELEGATE_POLL_SECS:-20}"
IDLE_STREAK="${PI_DELEGATE_IDLE_STREAK:-3}"
MAX_HOURS="${PI_DELEGATE_WATCH_HOURS:-12}"
# A freshly booted child is NOT busy either: between the prompt landing and the
# first "Working..." frame it looks exactly like a finished one. Without a rising
# edge the watcher reports "finished" during startup — the same mistake as calling
# a not-yet-ready TUI ready. Require evidence the child actually started: either we
# observed it busy, or its context gauge moved off 0.0% (it consumed the prompt).
MIN_GRACE="${PI_DELEGATE_MIN_GRACE_SECS:-45}"
# Delivery retry belongs to the session-bound mailbox consumer.

mkdir -p "$MAILBOX" "$MAILBOX/ack"


# pi renders busy as a braille spinner + "Working" ("── ⠴ Working ────"), older TUIs as
# "Working...". Matching only the dotted form made every pi child look idle from birth
# and fired five false completions in one round (2026-09-07).
pane_busy() {
	local pane
	pane=$(tmux capture-pane -t "$TARGET" -p 2>/dev/null) || return 2
	printf '%s' "$pane" | grep -qE '[⠀-⣿] Working|Working\.\.\.|esc to interrupt'
}


pane_cost() {
	tmux capture-pane -t "$TARGET" -p 2>/dev/null |
		grep -oE '\$[0-9]+\.[0-9]+' | tail -1
}

# Non-zero context gauge == the child consumed its prompt and did some work.
pane_started() {
	local g
	g=$(tmux capture-pane -t "$TARGET" -p 2>/dev/null |
		grep -oE '[0-9]+\.[0-9]+%/' | tail -1)
	[ -n "$g" ] && [ "$g" != "0.0%/" ]
}

started_at=${PI_DELEGATE_STARTED_AT:-$(date +%s)}
deadline=$(( started_at + MAX_HOURS * 3600 ))
streak=0
seen_busy=0
goal_sent=0
verdict="idle"

# A result or blocker is terminal for the watcher, not proof the work passed.
# Keep the old PARENT handshake for children launched before this contract.
# Exclude template placeholders and ACK/progress chatter from the new format.
RESULT_LINE_RE='^[[:space:]]*[^[:space:]<>][^<>]*: (PASS|BLOCKER|DONE|FAILED) ([[:xdigit:]]{7,40}|none) - [^[:space:]<>]+([[:space:]]+ci:[0-9]+)?([[:space:]]+pr:[1-9][0-9]*)?[[:space:]]*$'

child_reported_result() {
	local pane
	pane=$(tmux capture-pane -t "$TARGET" -J -p -S -400 2>/dev/null) || return 1
	# Join terminal wrapping, and avoid grep -q/pipefail SIGPIPE on long histories.
	grep -qE "^ ?PARENT: .*\\b(done|accepted)\\b|$RESULT_LINE_RE" <<< "$pane"
}

# Pull the last matching line verbatim plus its STATUS/SHA/PATH fields. The
# task name may itself contain a colon ("example: nested task: PASS ..."), so
# the fields are lifted off the end of the line instead of split on the first
# colon.
result_fields_from_pane() {
	local pane line tail_match
	pane=$(tmux capture-pane -t "$TARGET" -J -p -S -400 2>/dev/null) || return 0
	line=$(grep -E "$RESULT_LINE_RE" <<< "$pane" | tail -1)
	line="${line#"${line%%[![:space:]]*}"}"
	line="${line%"${line##*[![:space:]]}"}"
	result_line="$line"
	result_status=""
	result_sha=""
	result_path=""
	[ -n "$line" ] || return 0
	tail_match=$(grep -oE '(PASS|BLOCKER|DONE|FAILED)[[:space:]]+([[:xdigit:]]{7,40}|none)[[:space:]]+-[[:space:]]+[^[:space:]<>]+' <<< "$line" | tail -1)
	[ -n "$tail_match" ] || return 0
	read -r result_status result_sha _dash result_path <<< "$tail_match"
}

while :; do
	# Long-lived children need fewer tmux captures; keep the short startup poll
	# for rising-edge detection, grace, /goal and mailbox behaviour unchanged.
	poll_interval="$POLL_SECS"
	if [ $(( $(date +%s) - started_at )) -ge 600 ] && [ -z "${PI_DELEGATE_POLL_SECS:-}" ]; then
		poll_interval=60
	fi
	sleep "$poll_interval"
	if ! tmux has-session -t "${TARGET%%:*}" 2>/dev/null ||
		! tmux list-windows -t "${TARGET%%:*}" -F '#{window_name}' 2>/dev/null |
		grep -qxF "${TARGET#*:}"; then
		verdict="window-gone"
		break
	fi
	# PR conflicts/red checks cannot be cured by waiting in ci_wait. Keep the
	# lane open while the watchdog sends durable parent + child steering.
	watchdog="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../../../../../bin/delegate-watchdog"
	if [ -n "$LANE_MANIFEST" ] && [ -f "$LANE_MANIFEST" ] && [ -x "$watchdog" ] && ! child_reported_result; then
		"$watchdog" "$LANE_MANIFEST" "$TARGET" "$PARENT"
		if [ "$?" = 10 ]; then
			streak=0
			if [ "$(date +%s)" -ge "$deadline" ]; then verdict="watch-timeout-${MAX_HOURS}h"; break; fi
			continue
		fi
	fi
	if pane_busy; then
		seen_busy=1
		streak=0
	else
		streak=$((streak + 1))
		elapsed=$(( $(date +%s) - started_at ))
		# Only trust an idle streak once the child demonstrably started, and never
		# inside the startup grace window.
		if [ "$streak" -ge "$IDLE_STREAK" ] && [ "$elapsed" -ge "$MIN_GRACE" ] &&
			{ [ "$seen_busy" = "1" ] || pane_started; }; then
			# Self-continue before bothering the parent: a child that stops after one
			# slice without a result or blocker gets a /goal (goal.ts keeps it working
			# until an evaluator confirms the condition, PI_GOAL_MAX_TURNS turns).
			# Measured 2026-09-28: 7/7 gpt-6-luna delegates stopped after one slice
			# calling remaining work "blocked"; each cost a parent round-trip.
			if [ -n "${PI_DELEGATE_GOAL:-}" ] && [ "$goal_sent" = "0" ] && ! child_reported_result; then
				goal_sent=1
				# Only the captured child's ID, never whoever occupies TARGET now.
				child_id="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("child_session_id") or "")' "$LANE_MANIFEST" 2>/dev/null)"
				if [ -n "$child_id" ]; then
					sender="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../../../../../bin/delegate-send"
					"$sender" "session:$child_id" --text "/goal ${PI_DELEGATE_GOAL}" || true
				fi
				streak=0
				continue
			fi
			verdict="idle"
			break
		fi
		# Never started at all: the prompt was dropped. That is a distinct failure
		# and the parent must hear about it, not be told the work is done.
		if [ "$elapsed" -ge $(( MIN_GRACE * 4 )) ] && [ "$seen_busy" = "0" ] && ! pane_started; then
			verdict="never-started (prompt dropped - child has NO task)"
			break
		fi
	fi
	if [ "$(date +%s)" -ge "$deadline" ]; then
		verdict="watch-timeout-${MAX_HOURS}h"
		break
	fi
done

ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
cost="$(pane_cost)"
tail_txt="$(tmux capture-pane -t "$TARGET" -p 2>/dev/null |
	grep -v '^[[:space:]]*$' | grep -vE '^─|^↑[0-9]' | tail -12)"
result_line=""
result_status=""
result_sha=""
result_path=""
result_fields_from_pane
[ -n "$result_status" ] || result_status="$verdict"

# Durable record first: if the nudge is dropped, this is still here.
rec="$MAILBOX/${ts//:/-}_${RUN_ID}.mail"

close_lane_manifest "$result_line" "$result_status" "$result_sha" "$result_path" "$ts" "$cost" "$rec"

# Only launch-time identity may address the completion. Old manifests remain
# durable but unaddressed; operators must explicitly map them, never guess.
MAILBOX_PARENT="$PARENT"
PARENT_SESSION_ID=""
if [ -n "$LANE_MANIFEST" ] && [ -f "$LANE_MANIFEST" ]; then
	PARENT_SESSION_ID="$(python3 -c 'import json,re,sys; s=json.load(open(sys.argv[1])).get("parent_session_id", ""); print(s if isinstance(s,str) and re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9])?",s) else "")' "$LANE_MANIFEST" 2>/dev/null)"
fi

{
	echo "# Delegation finished: ${TASK:-$RUN_ID}"
	echo
	echo "- window: \`$TARGET\`"
	echo "- parent-pane: \`$MAILBOX_PARENT\`"
	echo "- recipient_session_id: \`$PARENT_SESSION_ID\`"
	echo "- parent-window: \`$PARENT\`"
	echo "- run id: \`$RUN_ID\`"
	echo "- cwd: \`$CHILD_CWD\`"
	echo "- verdict: **$verdict**"
	echo "- cost: ${cost:-unknown}"
	echo "- at: $ts"
	if [ -n "$result_line" ]; then
		echo
		echo '## Result'
		printf '%s\n' "$result_line"
	fi
	if [ -n "$CHILD_CWD" ] && [ -f "$CHILD_CWD/scripts/reap-finished-work.sh" ]; then
		echo
		echo '## Finished-work dry-run'
		echo '```'
		timeout 90 bash "$CHILD_CWD/scripts/reap-finished-work.sh" --dry-run || echo 'reaper unavailable'
		echo '```'
	fi
	echo
	echo '## Last output'
	echo '```'
	printf '%s\n' "$tail_txt"
	echo '```'
} >"${rec}.tmp" 2>/dev/null
mv -- "${rec}.tmp" "$rec"

# No keystroke fallback: the old pane may now contain another chat or shell.
# The session-addressed record survives until the intended parent resumes.
echo "watch-child: record $rec queued for session ${PARENT_SESSION_ID:-UNKNOWN (quarantine)}; no pane nudge" >&2
exit 0
