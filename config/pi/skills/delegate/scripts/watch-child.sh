#!/bin/bash
# watch-child.sh — close the delegation feedback loop.
#
# A delegated child runs to completion and then sits idle forever. Nothing wakes
# the parent, so work stops until a human looks. Measured 2026-08-29: nine agents
# finished, and 22.5 hours passed with zero merges because nobody nudged.
#
# This watcher is detached from both parent and child. It polls the child's pane,
# and when the child goes idle it (a) writes a durable record to the mailbox and
# (b) sends the parent a one-line nudge.
#
# Two channels on purpose. The nudge is a keystroke and keystrokes get dropped —
# a TUI that is mid-turn swallows them with no trace. The mailbox is the state,
# on persistent disk, and survives a dropped nudge, a reboot, and the child's
# worktree being removed. Never put the payload in the keystroke.
#
# A single nudge is not delivery (measured 2026-09-07: parent mid-turn with its
# operator swallowed the nudge; the operator noticed before the parent did). So
# the nudge is an at-least-once loop closed by an ACK: the parent acknowledges a
# record by moving it to $MAILBOX/ack/, and until that happens the watcher waits
# for the parent's pane to go idle and re-sends, up to PI_DELEGATE_MAX_NUDGES
# attempts spaced PI_DELEGATE_RENUDGE_SECS apart.
#
# usage: watch-child.sh <session:window> <parent-window> <run-id> <cwd> [task]
set -uo pipefail

TARGET="${1:?target window}"
PARENT="${2:?parent window}"
RUN_ID="${3:?run id}"
CHILD_CWD="${4:-}"
TASK="${5:-}"

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
RENUDGE_SECS="${PI_DELEGATE_RENUDGE_SECS:-300}"
MAX_NUDGES="${PI_DELEGATE_MAX_NUDGES:-8}"

mkdir -p "$MAILBOX" "$MAILBOX/ack"
LOCK="$MAILBOX/.nudge.lock"

# pi renders busy as a braille spinner + "Working" ("── ⠴ Working ────"), older TUIs as
# "Working...". Matching only the dotted form made every pi child look idle from birth
# and fired five false completions in one round (2026-09-07).
pane_busy() {
	local pane
	pane=$(tmux capture-pane -t "$TARGET" -p 2>/dev/null) || return 2
	printf '%s' "$pane" | grep -qE '[⠀-⣿] Working|Working\.\.\.|esc to interrupt'
}

parent_pane_busy_pattern='[⠀-⣿] Working|Working\.\.\.|esc to interrupt'

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

started_at=$(date +%s)
deadline=$(( started_at + MAX_HOURS * 3600 ))
streak=0
seen_busy=0
verdict="idle"

while :; do
	sleep "$POLL_SECS"
	if ! tmux has-session -t "${TARGET%%:*}" 2>/dev/null ||
		! tmux list-windows -t "${TARGET%%:*}" -F '#{window_name}' 2>/dev/null |
		grep -qxF "${TARGET#*:}"; then
		verdict="window-gone"
		break
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

# Durable record first: if the nudge is dropped, this is still here.
rec="$MAILBOX/${ts//:/-}_${RUN_ID}.md"
{
	echo "# Delegation finished: ${TASK:-$RUN_ID}"
	echo
	echo "- window: \`$TARGET\`"
	echo "- parent: \`$PARENT\`"
	echo "- run id: \`$RUN_ID\`"
	echo "- cwd: \`$CHILD_CWD\`"
	echo "- verdict: **$verdict**"
	echo "- cost: ${cost:-unknown}"
	echo "- at: $ts"
	echo
	echo '## Last output'
	echo '```'
	printf '%s\n' "$tail_txt"
	echo '```'
} >"$rec" 2>/dev/null

# Then the nudge. Refuse to send if the parent could not be resolved or no longer
# exists: nudging a guessed window delivers someone else's completion report into an
# unrelated agent's input box, which happened across two sessions on 2026-08-31. The
# mailbox record above is already written, so nothing is lost by staying silent.
parent_ok=1
case "$PARENT" in
	unknown | "") parent_ok=0 ;;
esac
if [ "$parent_ok" = "1" ]; then
	case "$PARENT" in
	%*) tmux list-panes -a -F '#{pane_id}' 2>/dev/null | grep -qxF "$PARENT" || parent_ok=0 ;;
	*) tmux list-panes -a -F '#{session_name}:#{window_name}' 2>/dev/null | grep -qxF "$PARENT" || parent_ok=0 ;;
	esac
fi
if [ "$parent_ok" = "0" ]; then
	echo "watch-child: parent '$PARENT' unresolved or gone; record written to $rec, no nudge sent" >&2
	exit 0
fi

parent_busy() {
	tmux capture-pane -t "$PARENT" -p 2>/dev/null |
		grep -qE "$parent_pane_busy_pattern"
}

parent_gone() {
	case "$PARENT" in
	%*) ! tmux list-panes -a -F '#{pane_id}' 2>/dev/null | grep -qxF "$PARENT" ;;
	*) ! tmux list-panes -a -F '#{session_name}:#{window_name}' 2>/dev/null | grep -qxF "$PARENT" ;;
	esac
}

acked() {
	[ ! -e "$rec" ] || [ -e "$MAILBOX/ack/$(basename "$rec")" ]
}

send_nudge() {
	local attempt="$1"
	local nudge="DELEGATION FINISHED (nudge ${attempt}/${MAX_NUDGES}) — ${TASK:-$RUN_ID} in window ${TARGET} is now ${verdict} (cost ${cost:-unknown}). Full record: ${rec}. Read the record, decide what to do next, then ACKNOWLEDGE with: mv '${rec}' '${MAILBOX}/ack/' — unacknowledged records are re-nudged. The child is idle and will do nothing further on its own."
	(
		flock -w 120 9 || exit 0
		tmux send-keys -t "$PARENT" C-u 2>/dev/null || true
		sleep 0.4
		tmux send-keys -t "$PARENT" -l -- "$nudge" 2>/dev/null || true
		sleep 0.6
		tmux send-keys -t "$PARENT" C-m 2>/dev/null || true
		sleep 0.6
		tmux send-keys -t "$PARENT" Enter 2>/dev/null || true
		sleep 2
	) 9>"$LOCK"
}

attempt=1
while :; do
	# Prefer delivering into an idle parent: a mid-turn TUI swallows keystrokes.
	# Wait up to one re-nudge interval for idleness, then send anyway — an
	# at-least-once send into a busy pane still beats staying silent, because the
	# ack loop catches the drop.
	waited=0
	while parent_busy && [ "$waited" -lt "$RENUDGE_SECS" ]; do
		sleep 15
		waited=$((waited + 15))
		if acked; then break 2; fi
		if parent_gone; then
			echo "watch-child: parent '$PARENT' gone before nudge $attempt; record stays in $rec" >&2
			exit 0
		fi
	done
	send_nudge "$attempt"
	waited=0
	while [ "$waited" -lt "$RENUDGE_SECS" ]; do
		sleep 15
		waited=$((waited + 15))
		if acked; then break 2; fi
		if parent_gone; then
			echo "watch-child: parent '$PARENT' gone after nudge $attempt; record stays in $rec" >&2
			exit 0
		fi
	done
	attempt=$((attempt + 1))
	if [ "$attempt" -gt "$MAX_NUDGES" ]; then
		echo "watch-child: $MAX_NUDGES nudges sent, no ack; record stays in $rec" >&2
		exit 0
	fi
done
exit 0
