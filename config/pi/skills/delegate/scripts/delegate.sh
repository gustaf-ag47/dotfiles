#!/bin/bash
# delegate.sh — boot a fresh interactive pi sub-agent in a new tmux window of the
# CURRENT tmux session, hand it a brief, and tell it who its parent is.
#
# Why a script instead of ad-hoc tmux calls: every step below is a failure mode
# that has actually bitten a delegating agent.
#   * keystrokes sent before the TUI finished booting are swallowed silently
#   * a leftover dirty prompt line concatenates with the launch command
#     (observed: "build 100THINKING=medium ..." -> integer expected)
#   * a model whose quota pool is exhausted dies instantly and the delegation
#     looks "started" but produced nothing (Fable/overage can be empty while the
#     general pool is fine — probe, do not assume)
#   * multi-line prompts sent with send-keys submit early at the first newline
#
# Usage:
#   delegate.sh --brief <file> [--task "<one line>"] [options]
#   delegate.sh --task "<one line>" [options]
#
# Options:
#   --brief <file>     Markdown brief the child reads first (strongly recommended).
#   --task  <text>     One-line task summary; used in the prompt and window name.
#   --name  <name>     tmux window name (default: derived from --task).
#   --cwd   <dir>      Working directory for the child (default: $PWD).
#   --model <model>    Qualified model preferred; default: Pi's configured default.
#   --agent <bin>      Launcher binary (default: pi).
#   --provider <name>  Optional provider; usually use --model provider/model.
#   --worktree <branch>  Create a git worktree for <branch> off origin/main and use it as --cwd.
#   --session <name>   Target tmux session (default: auto-detected).
#   --no-probe         Skip the model availability probe (faster, riskier).
#   --dry-run          Print what would happen, change nothing.
set -euo pipefail

BRIEF="" TASK="" NAME="" CWD="$PWD" MODEL="${PI_DELEGATE_MODEL:-}" AGENT="pi"
PROVIDER="${PI_DELEGATE_PROVIDER:-}" WORKTREE="" SESSION="" PROBE=1 DRY=0

die() { echo "delegate: error: $*" >&2; exit 1; }

while [ $# -gt 0 ]; do
	case "$1" in
	--brief) BRIEF="${2:?}"; shift 2 ;;
	--task) TASK="${2:?}"; shift 2 ;;
	--name) NAME="${2:?}"; shift 2 ;;
	--cwd) CWD="${2:?}"; shift 2 ;;
	--model) MODEL="${2:?}"; shift 2 ;;
	--agent) AGENT="${2:?}"; shift 2 ;;
	--provider) PROVIDER="${2:?}"; shift 2 ;;
	--worktree) WORKTREE="${2:?}"; shift 2 ;;
	--session) SESSION="${2:?}"; shift 2 ;;
	--no-probe) PROBE=0; shift ;;
	--no-notify) NOTIFY=0; shift ;;
	--dry-run) DRY=1; shift ;;
	-h | --help) sed -n '2,30p' "$0"; exit 0 ;;
	*) die "unknown option: $1" ;;
	esac
done

[ -n "$BRIEF" ] || [ -n "$TASK" ] || die "need --brief and/or --task"
[ -z "$BRIEF" ] || [ -f "$BRIEF" ] || die "brief not found: $BRIEF"
command -v tmux >/dev/null || die "tmux not found"
command -v "$AGENT" >/dev/null || die "$AGENT not in PATH"

# ── the current tmux session ────────────────────────────────────────────────
if [ -z "$SESSION" ]; then
	if [ -n "${TMUX:-}" ]; then
		SESSION="$(tmux display-message -p '#S')"
	else
		SESSION="$(tmux list-sessions -F '#{session_attached} #{session_name}' 2>/dev/null |
			sort -rn | head -1 | cut -d' ' -f2-)"
	fi
fi
[ -n "$SESSION" ] || die "no tmux session found; pass --session"
tmux has-session -t "$SESSION" 2>/dev/null || die "no such tmux session: $SESSION"

# Resolve the parent from THIS pane, not from the session's active window:
# `tmux display-message -p '#S:#W'` reports whichever window the client is
# looking at, so an orchestrator spawning from a background pane told every
# child that its parent was some unrelated sibling.
# Resolve the parent deterministically. `tmux display-message -p '#S:#W'` reports the
# window the ATTACHED CLIENT is looking at, which is not necessarily the caller and is
# not even necessarily the caller's session: a child spawned from the Dotfiles session
# recorded its parent as Work-Driver, because that session had attached clients,
# and its completion nudge went to a stranger's window. Prefer $TMUX_PANE; otherwise
# walk our own process ancestry until it matches a pane pid. Never guess.
resolve_parent_window() {
	[ -n "${TMUX:-}" ] || { printf 'unknown'; return; }
	if [ -n "${TMUX_PANE:-}" ]; then
		printf '%s' "$TMUX_PANE"; return
	fi
	local panes pid match
	# Emit the immutable pane id (%N), not session:window. A window name targets the
	# ACTIVE pane at delivery time — with two operator conversations split over two
	# panes of one window, completion nudges were delivered to whichever conversation
	# happened to have focus (observed 2026-09-01, window 'speedup ci', panes 1 and 2).
	panes=$(tmux list-panes -a -F '#{pane_pid} #{pane_id}' 2>/dev/null)
	pid=$$
	while [ -n "$pid" ] && [ "$pid" -gt 1 ] 2>/dev/null; do
		match=$(printf '%s\n' "$panes" | awk -v p="$pid" '$1==p {sub(/^[0-9]+[ \t]+/, ""); print; exit}')
		[ -n "$match" ] && { printf '%s' "$match"; return; }
		pid=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')
	done
	printf 'unknown'
}
PARENT_WINDOW="$(resolve_parent_window)"

# ── worktree isolation (children that write code must not share a checkout) ──
if [ -n "$WORKTREE" ]; then
	repo_root="$(git -C "$CWD" rev-parse --show-toplevel 2>/dev/null)" || die "--worktree needs a git repo"
	wt_dir="${TMPDIR:-/tmp}/wt-${WORKTREE//\//-}"
	# Do not assume origin/main: this repo may use master (or anything else).
	# Ask the remote what its HEAD is, and fall back to the local branch.
	base_ref="$(git -C "$repo_root" symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null)"
	if [ -z "$base_ref" ]; then
		for cand in origin/main origin/master; do
			git -C "$repo_root" show-ref -q --verify "refs/remotes/$cand" && { base_ref="$cand"; break; }
		done
	fi
	[ -n "$base_ref" ] || base_ref="$(git -C "$repo_root" rev-parse --abbrev-ref HEAD)"
	if [ "$DRY" = "1" ]; then
		echo "would: git -C $repo_root worktree add $wt_dir -b $WORKTREE $base_ref"
	elif [ -d "$wt_dir" ]; then
		echo "delegate: reusing existing worktree $wt_dir"
	else
		git -C "$repo_root" fetch -q origin || true
		git -C "$repo_root" worktree add "$wt_dir" -b "$WORKTREE" "$base_ref" -q ||
			die "could not create worktree for $WORKTREE off $base_ref"
		echo "delegate: worktree $wt_dir on $WORKTREE (off $base_ref)"
	fi
	# A --worktree child gets a FRESH checkout of origin/main, so a brief that is
	# untracked in the parent checkout simply does not exist for it: the child is
	# told to read a path that is not there and invents a task instead. Copy the
	# brief in, preserving its repo-relative path so the child can commit it.
	if [ -n "$BRIEF" ] && [ "$DRY" != "1" ]; then
		brief_abs="$(realpath "$BRIEF")"
		brief_in_repo="$(realpath --relative-to="$repo_root" "$brief_abs" 2>/dev/null || true)"
		case "$brief_in_repo" in
		..* | "") brief_in_repo="DELEGATE_BRIEF.md" ;;
		esac
		if [ ! -f "$wt_dir/$brief_in_repo" ]; then
			mkdir -p "$wt_dir/$(dirname "$brief_in_repo")"
			cp "$brief_abs" "$wt_dir/$brief_in_repo"
			echo "delegate: copied brief into worktree as $brief_in_repo"
		fi
		BRIEF="$wt_dir/$brief_in_repo"
	fi
	CWD="$wt_dir"
fi
[ -d "$CWD" ] || die "cwd does not exist: $CWD"

# ── window name (unique) ────────────────────────────────────────────────────
if [ -z "$NAME" ]; then
	NAME="$(printf '%s' "${TASK:-$(basename "${BRIEF%.*}")}" | tr '[:upper:]' '[:lower:]' |
		tr -cs 'a-z0-9' '-' | sed 's/^-//; s/-$//' | cut -c1-24)"
	NAME="sub-${NAME:-agent}"
fi
base="$NAME" n=2
while tmux list-windows -t "$SESSION" -F '#W' 2>/dev/null | grep -qx "$NAME"; do
	NAME="${base}-${n}"; n=$((n + 1))
done

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
MODEL_ARGS=()
[ -z "$PROVIDER" ] || MODEL_ARGS+=(--provider "$PROVIDER")
[ -z "$MODEL" ] || MODEL_ARGS+=(--model "$MODEL")

if [ "$DRY" = "1" ]; then
	cat <<EOF
would delegate:
  session : $SESSION
  window  : $NAME
  cwd     : $CWD
  model   : $MODEL ($PROVIDER via $AGENT)
  brief   : ${BRIEF:-<none>}
  parent  : $PARENT_WINDOW (pid $PPID)
  run id  : $RUN_ID
EOF
	exit 0
fi

# ── probe the model: an exhausted quota pool dies instantly and silently ─────
if [ "$PROBE" = "1" ]; then
	printf 'delegate: probing %s ... ' "$MODEL"
	if probe_out=$(cd "$CWD" && timeout 120 "$AGENT" "${MODEL_ARGS[@]}" \
		--no-session -p "Reply with exactly: OK" 2>&1 | tail -1); then
		case "$probe_out" in
		*OK*) echo "ok" ;;
		*) echo "UNEXPECTED: $probe_out"
		   die "model $MODEL did not answer a trivial prompt; try another model (a quota pool may be exhausted)" ;;
		esac
	else
		echo "FAILED"
		echo "  $probe_out" >&2
		die "model $MODEL is not usable right now (quota/cooldown?); pass --model with an alternative"
	fi
fi

# ── boot the child ──────────────────────────────────────────────────────────
tmux new-window -t "$SESSION" -n "$NAME" -c "$CWD" -d
# Clear any buffered keystrokes on a dirty prompt line before typing the command.
tmux send-keys -t "$SESSION:$NAME" C-u 2>/dev/null || true
CHILD_ENV=(env "PI_DELEGATE_PARENT=$PARENT_WINDOW" "PI_DELEGATE_RUN_ID=$RUN_ID")
# tmux's server environment may predate this shell/profile. Pass only the
# explicitly selected profile/offline settings, never credentials in argv.
[ -z "${PI_CODING_AGENT_DIR:-}" ] || CHILD_ENV+=("PI_CODING_AGENT_DIR=$PI_CODING_AGENT_DIR")
[ -z "${PI_OFFLINE:-}" ] || CHILD_ENV+=("PI_OFFLINE=$PI_OFFLINE")
printf -v child_command '%q ' "${CHILD_ENV[@]}" "$AGENT" "${MODEL_ARGS[@]}"
tmux send-keys -t "$SESSION:$NAME" -l -- "$child_command"
tmux send-keys -t "$SESSION:$NAME" Enter

# Wait for the TUI to be ready; keystrokes sent too early are silently DISCARDED
# (observed: three agents booted, prompt sent, input box empty, context 0.0%).
# The model name is not a reliable readiness signal — it can be absent from the
# status bar while a long skills/extensions banner is still rendering. The
# context-percentage gauge only renders once the input loop is live, so use that.
# 60s was too short in practice: a long skills/extensions banner plus an update
# notice regularly pushed first render past it, the script warned and sent the
# prompt anyway, and the keystrokes were dropped with no trace.
ready=0
for _ in $(seq 1 180); do
	sleep 1
	if tmux capture-pane -t "$SESSION:$NAME" -p 2>/dev/null | grep -qE '[0-9]+\.[0-9]+%/'; then
		ready=1
		break
	fi
done
[ "$ready" = "1" ] || echo "delegate: warning: TUI readiness not confirmed after 180s" >&2
# The gauge rendering means the status bar is painted, NOT that the input loop
# accepts keys yet; that gap is where prompts vanish. Settle before typing.
sleep 8

# ── the handover prompt: ONE line (send-keys submits at newlines) ────────────
prompt="You are a delegated sub-agent with a fresh context window."
if [ -n "$BRIEF" ]; then
	brief_rel="$BRIEF"
	case "$BRIEF" in /*) brief_rel="$(realpath --relative-to="$CWD" "$BRIEF" 2>/dev/null || echo "$BRIEF")" ;; esac
	prompt="$prompt Read ${brief_rel} in full — it is your complete brief — then execute it."
fi
[ -n "$TASK" ] && prompt="$prompt Task: ${TASK}"
prompt="$prompt You were booted by the pi agent in tmux window '${PARENT_WINDOW}' (delegation run id ${RUN_ID}); the same ids are in your PI_DELEGATE_PARENT and PI_DELEGATE_RUN_ID env vars. Work in ${CWD}. Read AGENTS.md/CLAUDE.md in the repo before acting, record findings in-repo rather than only in your context, and state clearly when you are done or blocked."

# -l sends the string literally: without it tmux parses words like "Enter" or
# "Space" inside the prompt as key names. Submit separately, and send Enter
# twice — C-m alone is swallowed by the TUI often enough to matter.
send_prompt() {
	tmux send-keys -t "$SESSION:$NAME" C-u 2>/dev/null || true
	sleep 0.4
	tmux send-keys -t "$SESSION:$NAME" -l -- "$prompt"
	sleep 0.6
	tmux send-keys -t "$SESSION:$NAME" C-m
	sleep 0.6
	tmux send-keys -t "$SESSION:$NAME" Enter
}

# Verify the prompt was CONSUMED, not merely sent. An unready TUI drops
# keystrokes with no trace: the window looks booted, the input box is empty and
# context sits at 0.0% forever.
#
# The previous implementation inspected `tail -3` of the pane. The status bar
# carrying the gauge is followed by separator//hint lines, so the gauge is
# usually OUTSIDE that window — the 0.0% branch never fired and the function
# fell through to `return 0`, reporting success for a prompt that was discarded.
# Measured on 2026-08-29/30: 19 of 20 delegations reported success while the
# child sat idle at 0.0%.
#
# Scan the WHOLE pane and require positive evidence of consumption: the last
# gauge reading must be non-zero, or the agent must already be working.
prompt_landed() {
	local pane gauge
	pane=$(tmux capture-pane -t "$SESSION:$NAME" -p 2>/dev/null)
	printf '%s' "$pane" | grep -qE 'Working\.\.\.|esc to interrupt' && return 0
	gauge=$(printf '%s' "$pane" | grep -oE '[0-9]+\.[0-9]+%/' | tail -1)
	[ -n "$gauge" ] || return 1
	[ "$gauge" = "0.0%/" ] && return 1
	return 0
}

landed=0
for attempt in 1 2 3; do
	[ "$attempt" -gt 1 ] && echo "delegate: prompt not registered — re-send attempt $attempt" >&2
	send_prompt
	for _ in $(seq 1 15); do
		sleep 2
		if prompt_landed; then landed=1; break; fi
	done
	[ "$landed" = "1" ] && break
done
if [ "$landed" != "1" ]; then
	echo "delegate: ERROR: prompt never registered after 3 attempts." >&2
	echo "  The window exists but the child has NO task. Send it by hand:" >&2
	echo "    tmux send-keys -t $SESSION:$NAME -l -- '<prompt>'; tmux send-keys -t $SESSION:$NAME Enter" >&2
	echo "  Do not assume it is working: check the context gauge is off 0.0%." >&2
	DELEGATE_FAILED=1
fi

# ── close the feedback loop ─────────────────────────────────────────────────
# A child that finishes sits idle forever and nothing wakes the parent. Detach a
# watcher that nudges the parent when this child goes idle. It watches from the
# outside, so a child that crashes, wedges or simply forgets to report is still
# reported — the loop must not depend on the child's cooperation.
WATCHER="$(dirname "$0")/watch-child.sh"
if [ "${NOTIFY:-1}" = "1" ] && [ -x "$WATCHER" ]; then
	nohup "$WATCHER" "$SESSION:$NAME" "$PARENT_WINDOW" "$RUN_ID" "$CWD" "${TASK:-}" \
		>/dev/null 2>&1 &
	disown 2>/dev/null || true
	NOTIFY_STATE="watching (nudges $PARENT_WINDOW on idle)"
else
	NOTIFY_STATE="off"
fi

cat <<EOF
delegated -> $SESSION:$NAME
  model  : $MODEL ($PROVIDER)
  cwd    : $CWD
  brief  : ${BRIEF:-<none>}
  run id : $RUN_ID
  prompt : $([ "${DELEGATE_FAILED:-0}" = "1" ] && echo 'NOT REGISTERED - child has no task' || echo 'consumed (gauge off 0.0%)')
  notify : $NOTIFY_STATE
monitor:
  tmux capture-pane -t $SESSION:$NAME -p | tail -20
  tmux select-window -t $SESSION:$NAME     # to watch it live
EOF

# Exit non-zero when the child was booted but never received its task, so a
# caller spawning several in a loop can tell the difference instead of moving on.
[ "${DELEGATE_FAILED:-0}" = "1" ] && exit 3
exit 0
