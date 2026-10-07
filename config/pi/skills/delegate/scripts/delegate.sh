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
#   --worktree <branch>  Create a git worktree for <branch> off $WORKTREES and use it as --cwd.
#   --session <name>   Target tmux session (default: auto-detected).
#   --project <name>   Resolve session and cwd from `ws route <name>` (see docs/WORKSPACE.md).
#   --resume auto|confirm  Lane manifest resume policy read by `ws up` (default: confirm).
#   --no-probe         Skip the model availability probe (faster, riskier).
#   --when reset|waste|now  Queue work until quota is fresh or wasting (default now).
#   --dry-run          Print what would happen, change nothing.
# Worktrees land under $WORKTREES, a persistent mount; /tmp is refused. The
# parent and the completion-report target are session:window-name, resolved to
# a pane at send time (a bare %id from an older caller still works). At launch
# a lane manifest is written to <runs>/.lanes/<run-id>.json, where <runs> comes
# from `ws route`; `ws up`/watch-child.sh mark it closed.
# Jev observes only --task (never the brief), after validation/probing. It cannot
# change CLASS/MODEL. PI_JEV_MODE=off disables observation; failures never block.
set -euo pipefail

BRIEF="" TASK="" NAME="" CWD="$PWD" MODEL="${PI_DELEGATE_MODEL:-}" AGENT="pi"
CLASS="${PI_LLM_CLASS:-build}" MODEL_EXPLICIT=0
PROVIDER="${PI_DELEGATE_PROVIDER:-}" WORKTREE="" SESSION="" PROBE=1 DRY=0 WHEN=now
PROJECT="" RESUME=confirm SESSION_EXPLICIT=0 CWD_EXPLICIT=0
ORIGINAL_ARGS=("$@")

die() { echo "delegate: error: $*" >&2; exit 1; }

while [ $# -gt 0 ]; do
	case "$1" in
	--brief) BRIEF="${2:?}"; shift 2 ;;
	--task) TASK="${2:?}"; shift 2 ;;
	--name) NAME="${2:?}"; shift 2 ;;
	--cwd) CWD="${2:?}"; CWD_EXPLICIT=1; shift 2 ;;
	--model) MODEL="${2:?}"; MODEL_EXPLICIT=1; shift 2 ;;
	--class) CLASS="${2:?}"; shift 2 ;;
	--when) WHEN="${2:?}"; shift 2 ;;
	--agent) AGENT="${2:?}"; shift 2 ;;
	--provider) PROVIDER="${2:?}"; shift 2 ;;
	--worktree) WORKTREE="${2:?}"; shift 2 ;;
	--session) SESSION="${2:?}"; SESSION_EXPLICIT=1; shift 2 ;;
	--project) PROJECT="${2:?}"; shift 2 ;;
	--resume) RESUME="${2:?}"; shift 2 ;;
	--no-probe) PROBE=0; shift ;;
	--no-notify) NOTIFY=0; shift ;;
	--dry-run) DRY=1; shift ;;
	-h | --help) sed -n '2,30p' "$0"; exit 0 ;;
	*) die "unknown option: $1" ;;
	esac
done

case "$WHEN" in now|reset|waste) ;; *) die "--when must be reset, waste or now" ;; esac
case "$RESUME" in auto|confirm) ;; *) die "--resume must be auto or confirm" ;; esac
[ -n "$BRIEF" ] || [ -n "$TASK" ] || die "need --brief and/or --task"
if [ "$WHEN" != now ]; then
	# Preserve every argument except --when, including --worktree: worktree
	# creation belongs to the actual launch, not the time of enqueue.
	cmd=("$0")
	set -- "${ORIGINAL_ARGS[@]}"
	while [ "$#" -gt 0 ]; do
		if [ "$1" = --when ]; then shift 2; else cmd+=("$1"); shift; fi
	done
	if [ "$DRY" = 1 ]; then printf 'would queue: %q ' "${cmd[@]}"; echo; exit 0; fi
	command -v llm-schedule >/dev/null || die "llm-schedule not in PATH"
	llm-schedule add --class "$CLASS" --prefer any -- "${cmd[@]}"
	exit
fi
[ -z "$BRIEF" ] || [ -f "$BRIEF" ] || die "brief not found: $BRIEF"
command -v tmux >/dev/null || die "tmux not found"
command -v "$AGENT" >/dev/null || die "$AGENT not in PATH"

# ── --project: session and cwd come from the workspace reconciler ────────────
PROJECT_RUNS=""
if [ -n "$PROJECT" ]; then
	command -v ws >/dev/null 2>&1 || die "--project needs bin/ws on PATH"
	project_route="$(ws route "$PROJECT")" || die "ws route $PROJECT failed"
	read -r project_session _project_prefix project_cwd PROJECT_RUNS <<<"$project_route"
	[ "$SESSION_EXPLICIT" = "1" ] || SESSION="$project_session"
	[ "$CWD_EXPLICIT" = "1" ] || CWD="$project_cwd"
fi

# ── the current tmux session ────────────────────────────────────────────────
if [ -z "$SESSION" ]; then
	if [ -n "${TMUX:-}" ]; then
		if [ -n "${TMUX_PANE:-}" ]; then
			SESSION="$(tmux display-message -p -t "$TMUX_PANE" '#{session_id}')"
		else
			SESSION="$(tmux display-message -p '#{session_id}')"
		fi
	else
		SESSION="$(tmux list-sessions -F '#{session_attached} #{session_name}' 2>/dev/null |
			sort -rn | head -1 | cut -d' ' -f2-)"
	fi
fi
[ -n "$SESSION" ] || die "no tmux session found; pass --session"
tmux has-session -t "$SESSION" 2>/dev/null || die "no such tmux session: $SESSION"

# tmux accepts a session by name or by its numeric id ($0, $1, ...); both are
# "valid" per has-session above. A raw id stored verbatim in the lane manifest
# cannot be resolved later (the id changes across server restarts and ws route
# only knows names), so normalize to the current session NAME once, here.
normalized_session="$(tmux display-message -p -t "$SESSION:" '#{session_name}' 2>/dev/null)" || true
[ -n "$normalized_session" ] && SESSION="$normalized_session"

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
	# Workspace-as-code: parents are addressed as session:window-name so they
	# survive a tmux server restart (pane ids do not). $TMUX_PANE still pins the
	# EXACT calling pane -t, so this is not the client-focus bug the previous
	# pane-id-only approach guarded against; -t "$TMUX_PANE" is deterministic
	# regardless of which pane is focused. Two independent conversations sharing
	# one window still collide on this name — give each its own window.
	if [ -n "${TMUX_PANE:-}" ]; then
		tmux display-message -p -t "$TMUX_PANE" '#{session_name}:#{window_name}' 2>/dev/null && return
		printf '%s' "$TMUX_PANE"; return
	fi
	local panes pid match
	panes=$(tmux list-panes -a -F '#{pane_pid} #{session_name}:#{window_name}' 2>/dev/null)
	pid=$$
	while [ -n "$pid" ] && [ "$pid" -gt 1 ] 2>/dev/null; do
		match=$(printf '%s\n' "$panes" | awk -v p="$pid" '$1==p {sub(/^[0-9]+[ \t]+/, ""); print; exit}')
		[ -n "$match" ] && { printf '%s' "$match"; return; }
		pid=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')
	done
	printf 'unknown'
}
PARENT_WINDOW="$(resolve_parent_window)"
# $TMUX_PANE pins the exact pane regardless of window name collisions; kept as
# a fallback field on the manifest for when PARENT_WINDOW's window name turns
# out not to be a reliable address (see check below).
PARENT_PANE="${TMUX_PANE:-unknown}"

# session:window-name only survives a tmux restart if the name is unique in
# its session and not a generic shell name nobody meant to make addressable.
# Warn loudly rather than fail: a stale/ambiguous parent means a completion
# report could land on the wrong pane, not that delegation should be blocked.
check_parent_window_name() {
	case "$PARENT_WINDOW" in
	*:*) ;;
	*) return ;;
	esac
	local parent_session="${PARENT_WINDOW%%:*}" parent_window_name="${PARENT_WINDOW#*:}" matches
	case "$parent_window_name" in
	zsh | bash | pi)
		echo "delegate: warning: parent window '$PARENT_WINDOW' has a generic name ('$parent_window_name'); rename it (tmux rename-window) so completion reports land reliably. Recording parent_pane=$PARENT_PANE as a fallback." >&2
		return
		;;
	esac
	# grep -c returns 1 (no matches) as often as 0 (matches found); a bare
	# `var=$(... | grep -c ...)` assignment propagates THAT exit status under
	# set -e, killing the whole script on the common zero-match case.
	matches="$(tmux list-windows -t "$parent_session" -F '#{window_name}' 2>/dev/null | grep -cx "$parent_window_name")" || true
	if [ "${matches:-0}" -gt 1 ] 2>/dev/null; then
		echo "delegate: warning: parent window name '$parent_window_name' is not unique in session '$parent_session' ($matches matches); rename it (tmux rename-window) so completion reports land reliably. Recording parent_pane=$PARENT_PANE as a fallback." >&2
	fi
}
check_parent_window_name

# ── worktree isolation (children that write code must not share a checkout) ──
# Fail closed: WORKTREES must be set to a persistent mount, never /tmp (tmpfs
# loses every worktree on reboot; 22 were found there on 2026-10-07).
worktrees_guard() {
	[ -n "${WORKTREES:-}" ] || die "WORKTREES is not set; see config/environment.d/workspace.conf"
	case "$WORKTREES" in
	/tmp | /tmp/*) die "WORKTREES must not be under /tmp: $WORKTREES" ;;
	esac
	[ -d "$WORKTREES" ] || die "WORKTREES does not exist: $WORKTREES"
	if command -v findmnt >/dev/null 2>&1; then
		fstype="$(findmnt -no FSTYPE -T "$WORKTREES" 2>/dev/null)"
		case "$fstype" in
		tmpfs | ramfs) die "WORKTREES ($WORKTREES) is on $fstype, not a persistent mount" ;;
		esac
	fi
}
if [ -n "$WORKTREE" ]; then
	worktrees_guard
	repo_root="$(git -C "$CWD" rev-parse --show-toplevel 2>/dev/null)" || die "--worktree needs a git repo"
	wt_dir="$WORKTREES/wt-${WORKTREE//\//-}"
	mkdir -p "$WORKTREES"
	# Do not assume origin/main: this repo may use master (or anything else).
	# Ask the remote what its HEAD is, and fall back to the local branch.
	# A plain `var=$(cmd)` assignment propagates cmd's own exit status under
	# set -e: a repo with no origin/HEAD symbolic ref (shallow/CI checkouts
	# routinely have none) killed the whole script here before this had a
	# chance to fall through to the origin/main / origin/master candidates.
	base_ref="$(git -C "$repo_root" symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null)" || true
	if [ -z "$base_ref" ]; then
		for cand in origin/main origin/master; do
			git -C "$repo_root" show-ref -q --verify "refs/remotes/$cand" && { base_ref="$cand"; break; }
		done
	fi
	[ -n "$base_ref" ] || base_ref="$(git -C "$repo_root" rev-parse --abbrev-ref HEAD 2>/dev/null)" || true
	[ -n "$base_ref" ] || die "could not resolve a base ref for --worktree $WORKTREE"
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
[ "$DRY" = "1" ] || [ -d "$CWD" ] || die "cwd does not exist: $CWD"

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
if [ "$MODEL_EXPLICIT" = "0" ]; then
	ROUTE_URL="http://127.0.0.1:${CC_PROXY_PORT:-8788}/_route?class=${CLASS}"
	MODEL="$(curl -fsS "$ROUTE_URL" 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); p=d.get("preferred") or d.get("first_routable") or {}; print(p.get("provider","")+"/"+p.get("model", ""))' || true)"
	[ -n "$MODEL" ] || MODEL="${PI_DELEGATE_MODEL:-openai-codex/gpt-6-luna}"
fi
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
  parent  : $PARENT_WINDOW (pid $PPID, parent_pane $PARENT_PANE)
  run id  : $RUN_ID
EOF
	exit 0
fi

# Wait for the selected provider to become routable before spending a probe request.
if [ "$PROBE" = "1" ] && command -v llm-wait >/dev/null 2>&1; then
  selected_provider="$PROVIDER"
  if [ -z "$selected_provider" ] && [[ "$MODEL" == */* ]]; then selected_provider="${MODEL%%/*}"; fi
  case "$selected_provider" in openai-codex) wait_provider=codex ;; *) wait_provider="$selected_provider" ;; esac
  if [ -n "$wait_provider" ]; then
    route_model="${MODEL#*/}"
    case "$route_model" in claude-*) ;; *) route_model="claude-sonnet-5" ;; esac
    if llm-wait --until "$wait_provider.routable" --model "$route_model" --max "${PI_DELEGATE_WAIT_MAX:-2h}"; then
      :
    else
      wait_status=$?
      if [ "$wait_status" = "2" ] && [ "$wait_provider" = "codex" ]; then
        echo "delegate: Codex quota wait timed out; falling back to Anthropic sonnet"
        MODEL="anthropic/claude-sonnet-5"
        PROVIDER=anthropic
        MODEL_ARGS=(--provider "$PROVIDER" --model "claude-sonnet-5")
      else
        die "waiting for $wait_provider routing failed (status $wait_status)"
      fi
    fi
  fi
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

# Observe one short task description, not the brief or repository contents.
# The classifier records metadata only; its output is deliberately not evaluated
# or assigned to CLASS/MODEL. Dry runs and queued jobs have already returned.
if [ "${PI_JEV_MODE:-observe}" != off ] && [ -n "$TASK" ]; then
	delegate_dir="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
	jev_helper="$delegate_dir/../../../../../bin/jev-classify"
	if [ -x "$jev_helper" ] && command -v timeout >/dev/null 2>&1; then
		printf '%s' "$TASK" | timeout 5 "$jev_helper" --task-stdin --source delegate >/dev/null 2>&1 || true
	fi
fi

# ── boot the child ──────────────────────────────────────────────────────────
if command -v llm-usage >/dev/null 2>&1; then
  capacity_json=$(llm-usage --capacity --json 2>/dev/null) || capacity_json=
  if [ -n "$capacity_json" ] && command -v python3 >/dev/null 2>&1; then
    capacity=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["capacity"])' "$capacity_json" 2>/dev/null) || capacity=
    if [[ "$capacity" =~ ^[0-9]+$ ]] && [ "$capacity" -le 0 ]; then
      echo 'delegate: WARNING: no additional heavy sessions are safe for the next 2h (5h capacity estimate)' >&2
    fi
  fi
fi
# The colon makes numeric names unambiguously session targets, not window indexes.
tmux new-window -t "${SESSION}:" -n "$NAME" -c "$CWD" -d
# Clear any buffered keystrokes on a dirty prompt line before typing the command.
tmux send-keys -t "$SESSION:$NAME" C-u 2>/dev/null || true
CHILD_ENV=(env "PI_DELEGATE_PARENT=$PARENT_WINDOW" "PI_DELEGATE_RUN_ID=$RUN_ID" "PI_LLM_CLASS=$CLASS")
# Expose the brief path so merge-pr.sh (and the child itself) can find it without
# re-deriving it from the prompt text. Absolute, so it resolves regardless of cwd.
if [ -n "$BRIEF" ]; then
	brief_abs_for_env="$(realpath "$BRIEF" 2>/dev/null || echo "$BRIEF")"
	CHILD_ENV+=("PI_DELEGATE_BRIEF=$brief_abs_for_env")
fi
# tmux's server environment may predate this shell/profile. Pass only the
# explicitly selected profile/offline settings, never credentials in argv.
[ -z "${PI_CODING_AGENT_DIR:-}" ] || CHILD_ENV+=("PI_CODING_AGENT_DIR=$PI_CODING_AGENT_DIR")
[ -z "${PI_OFFLINE:-}" ] || CHILD_ENV+=("PI_OFFLINE=$PI_OFFLINE")
[ -z "${PI_JEV_MODE:-}" ] || CHILD_ENV+=("PI_JEV_MODE=$PI_JEV_MODE")
printf -v child_command '%q ' "${CHILD_ENV[@]}" "$AGENT" "${MODEL_ARGS[@]}"
tmux send-keys -t "$SESSION:$NAME" -l -- "$child_command"
tmux send-keys -t "$SESSION:$NAME" Enter

# ── lane manifest: survives a tmux/server restart, unlike the pane itself ────
RUNS_DIR="$PROJECT_RUNS"
if [ -z "$RUNS_DIR" ] && command -v ws >/dev/null 2>&1; then
	fallback_route="$(ws route "$(printf '%s' "$SESSION" | tr '[:upper:]' '[:lower:]')" 2>/dev/null)" || true
	[ -z "$fallback_route" ] || read -r _fb_session _fb_prefix _fb_cwd RUNS_DIR <<<"$fallback_route"
fi
[ -n "$RUNS_DIR" ] || RUNS_DIR="${NOTES:-$HOME/.local/state/pi}/.unrouted-lanes"
LANE_DIR="$RUNS_DIR/.lanes"
LANE_MANIFEST="$LANE_DIR/$RUN_ID.json"
if mkdir -p "$LANE_DIR" 2>/dev/null && command -v python3 >/dev/null 2>&1; then
	# <<- strips only LEADING TABS, and strips every one of them from every
	# line, so python's own indentation below is built from spaces, not tabs.
	python3 - "$LANE_MANIFEST" "$SESSION" "$NAME" "$CWD" "$WORKTREE" "$MODEL" "${BRIEF:-}" "$PARENT_WINDOW" "$RESUME" "$RUN_ID" "$PARENT_PANE" <<-'PY'
	import json, sys, datetime
	(path, session, window, cwd, branch, model, brief, parent, resume, run_id, parent_pane) = sys.argv[1:12]
	manifest = {
	    "run_id": run_id,
	    "session": session,
	    "window": window,
	    "cwd": cwd,
	    "branch": branch,
	    "model": model,
	    "brief": brief,
	    "pi_session": None,
	    "parent": parent,
	    "parent_pane": parent_pane,
	    "resume": resume,
	    "status": "open",
	    "created_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
	}
	with open(path, "w", encoding="utf-8") as handle:
	    json.dump(manifest, handle, indent=2)
	    handle.write("\n")
	PY
else
	echo "delegate: warning: could not write lane manifest at $LANE_MANIFEST" >&2
fi

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
prompt="$prompt You were booted by the pi agent in tmux window '${PARENT_WINDOW}' (delegation run id ${RUN_ID}); the same ids are in your PI_DELEGATE_PARENT and PI_DELEGATE_RUN_ID env vars. Work in ${CWD}. Read AGENTS.md/CLAUDE.md in the repo before acting and record findings in-repo. Send the parent only a result or blocker, once, as one line: <task>: <PASS|BLOCKER|DONE|FAILED> <sha-or-none> - <report path>. No ACK, receipt or relay messages. At 300k tokens of context (the TUI footer's absolute count, not a percentage), write a handover file with remaining work and evidence, send its path in that line, and stop."

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
# Default self-continue condition for briefed children (see watch-child.sh).
if [ -n "$BRIEF" ] && [ -z "${PI_DELEGATE_GOAL:-}" ]; then
	PI_DELEGATE_GOAL="every numbered item under Your job in ${brief_rel:-$BRIEF} is completed or has a documented operator decision, applicable gates have been run and reported, and findings are recorded at the path in the brief. Report blockers truthfully; never commit or push the operator Vault. Send the parent one result or blocker line with a report path."
fi
export PI_DELEGATE_GOAL
if [ "${NOTIFY:-1}" = "1" ] && [ -x "$WATCHER" ]; then
	# setsid: a parent that spawns from an agent tool-call shell has its whole
	# process group killed when the call returns; nohup alone did not survive that
	# (2026-09-28: zero watchers alive after 7 delegations, no nudges ever landed).
	if command -v systemd-run >/dev/null 2>&1 && systemd-run --user --quiet --collect \
		--setenv=PI_DELEGATE_GOAL="$PI_DELEGATE_GOAL" --setenv=PI_DELEGATE_MAILBOX="${PI_DELEGATE_MAILBOX:-$HOME/.pi/agent/delegate-mailbox}" \
		--unit "pi-delegate-watch-${RUN_ID}" "$WATCHER" "$SESSION:$NAME" "$PARENT_WINDOW" "$RUN_ID" "$CWD" "${TASK:-}" "$LANE_MANIFEST" 2>/dev/null; then
		NOTIFY_STATE="watching via systemd unit pi-delegate-watch-${RUN_ID} (nudges $PARENT_WINDOW on idle)"
	else
		setsid -f "$WATCHER" "$SESSION:$NAME" "$PARENT_WINDOW" "$RUN_ID" "$CWD" "${TASK:-}" "$LANE_MANIFEST" >/dev/null 2>&1 </dev/null
		NOTIFY_STATE="watching via setsid (nudges $PARENT_WINDOW on idle)"
	fi
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
