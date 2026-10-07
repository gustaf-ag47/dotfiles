#!/usr/bin/env bash
set -euo pipefail

# Read-only inventory of the in-flight work on THIS machine, for a handoff.
# Prints machine-readable TSV records to stdout and a one-line human summary
# to stderr. Changes nothing; touches no network.
#
# Records (tab-separated):
#   PANE      <session:window.pane>  <command>  <active|waiting|idle|dead>  <last line>
#   REPO      <path>  <branch>  dirty=N  unpushed=N  stashes=N  age_days=N  <current|stale>
#   WORKTREE  <main repo path>  <path>  <branch>  dirty=N  unpushed=N
#
# REPO rows appear only for repos with something to hand over (dirty files,
# commits on no remote, or stashes). "unpushed" counts commits reachable from
# HEAD but from no remote ref (git rev-list HEAD --not --remotes); a repo with
# no remote counts every commit, which is the point. "stale" is age-based
# triage input, not a verdict -- the judgement stays with the caller.
#
# Usage:
#   inventory.sh [--sync-root DIR]... [--stale-days N] [--agent-regex RE]
#                [--no-tmux] [--self-pane %ID]
#
# Defaults: sync roots from machines.conf for $(uname -n) (key src_root);
# stale after 60 days; agents matched by ^(pi|hermes|claude|codex)$ on the
# pane command; the pane running this script ($TMUX_PANE) is skipped.

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

stale_days=60
agent_re='^(pi|hermes|claude|codex)$'
no_tmux=0
self_pane="${TMUX_PANE:-}"
sync_roots=()

usage() {
	cat <<'EOF'
Usage: inventory.sh [--sync-root DIR]... [--stale-days N] [--agent-regex RE]
                    [--no-tmux] [--self-pane %ID]

Read-only inventory of in-flight work on this machine. TSV records on stdout
(PANE / REPO / WORKTREE, see the script header), human summary on stderr.
Defaults: sync roots from machines.conf for $(uname -n); stale after 60 days;
agent panes matched by ^(pi|hermes|claude|codex)$; $TMUX_PANE is skipped.
EOF
}

while [ $# -gt 0 ]; do
	case "$1" in
	--sync-root) sync_roots+=("$2"); shift 2 ;;
	--stale-days) stale_days="$2"; shift 2 ;;
	--agent-regex) agent_re="$2"; shift 2 ;;
	--no-tmux) no_tmux=1; shift ;;
	--self-pane) self_pane="$2"; shift 2 ;;
	-h | --help) usage; exit 0 ;;
	*) echo "inventory.sh: unknown option $1" >&2; usage >&2; exit 2 ;;
	esac
done

if [ ${#sync_roots[@]} -eq 0 ]; then
	# hostname(1) is missing on some machines; uname -n always works.
	host="$(uname -n)"
	if root="$("$script_dir/machines.sh" get "$host" src_root 2>/dev/null)"; then
		sync_roots+=("$root")
	else
		echo "inventory.sh: '$host' not in machines.conf; pass --sync-root" >&2
		exit 2
	fi
fi

now="$(date +%s)"
n_active=0 n_waiting=0 n_idle=0 n_dead=0 n_repos=0 n_stale=0 n_worktrees=0

# ---- tmux agent panes -------------------------------------------------------

classify_pane() { # <pane text> -> state
	local text="$1"
	if grep -q 'Resume this session with' <<<"$text"; then
		echo dead
	elif grep -qE 'Working|thinking|Ctrl\+C cancel|esc to interrupt' <<<"$text"; then
		echo active
	elif tail -n 3 <<<"$text" | grep -q '?'; then
		echo waiting
	else
		echo idle
	fi
}

scan_tmux() {
	local pane_id target cmd text state last
	while IFS=$'\t' read -r pane_id target cmd; do
		[ -n "$pane_id" ] || continue
		[ "$pane_id" = "$self_pane" ] && continue
		grep -qE "$agent_re" <<<"$cmd" || continue
		text="$(tmux capture-pane -p -t "$pane_id" | grep -v '^[[:space:]]*$' | tail -n 15 || true)"
		state="$(classify_pane "$text")"
		last="$(tail -n 1 <<<"$text" | tr '\t' ' ' | cut -c1-120)"
		case "$state" in
		active) n_active=$((n_active + 1)) ;;
		waiting) n_waiting=$((n_waiting + 1)) ;;
		idle) n_idle=$((n_idle + 1)) ;;
		dead) n_dead=$((n_dead + 1)) ;;
		esac
		printf 'PANE\t%s\t%s\t%s\t%s\n' "$target" "$cmd" "$state" "$last"
	done < <(tmux list-panes -a -F '#{pane_id}	#{session_name}:#{window_name}.#{pane_index}	#{pane_current_command}' 2>/dev/null || true)
}

# ---- git repos and worktrees ------------------------------------------------

repo_branch() {
	git -C "$1" symbolic-ref --short -q HEAD 2>/dev/null \
		|| git -C "$1" rev-parse --short HEAD 2>/dev/null \
		|| echo "(broken)"
}

repo_dirty() { git -C "$1" status --porcelain 2>/dev/null | grep -c . || true; }

repo_unpushed() {
	git -C "$1" rev-list --count HEAD --not --remotes 2>/dev/null || echo 0
}

repo_stashes() { git -C "$1" stash list 2>/dev/null | grep -c . || true; }

repo_age_days() {
	local ts
	ts="$(git -C "$1" log -1 --format=%ct 2>/dev/null || true)"
	[ -n "$ts" ] && echo $(((now - ts) / 86400)) || echo 0
}

declare -A seen=()

# A candidate found under a sync root may itself be a linked worktree of a
# main repo elsewhere; canonicalize to the main worktree (always first in
# `git worktree list`) so every checkout is attributed and counted once.
scan_repo() {
	local candidate="$1" main branch dirty unpushed stashes age class
	local wts=() wt wt_branch wt_dirty wt_unpushed
	mapfile -t wts < <(git -C "$candidate" worktree list --porcelain 2>/dev/null | sed -n 's/^worktree //p')
	main="${wts[0]:-$candidate}"
	[ -n "${seen[$main]:-}" ] && return 0
	seen[$main]=1
	branch="$(repo_branch "$main")"
	dirty="$(repo_dirty "$main")"
	unpushed="$(repo_unpushed "$main")"
	stashes="$(repo_stashes "$main")"
	if [ "$((dirty + unpushed + stashes))" -gt 0 ]; then
		age="$(repo_age_days "$main")"
		if [ "$age" -gt "$stale_days" ]; then class=stale; n_stale=$((n_stale + 1)); else class=current; fi
		n_repos=$((n_repos + 1))
		printf 'REPO\t%s\t%s\tdirty=%s\tunpushed=%s\tstashes=%s\tage_days=%s\t%s\n' \
			"$main" "$branch" "$dirty" "$unpushed" "$stashes" "$age" "$class"
	fi
	# Linked worktrees often live OUTSIDE the sync roots (/tmp, ~/.cache,
	# ~/worktrees) and never sync; always report them.
	for wt in "${wts[@]:1}"; do
		[ -n "${seen[$wt]:-}" ] && continue
		seen[$wt]=1
		[ -d "$wt" ] || continue
		wt_branch="$(repo_branch "$wt")"
		wt_dirty="$(repo_dirty "$wt")"
		wt_unpushed="$(repo_unpushed "$wt")"
		n_worktrees=$((n_worktrees + 1))
		printf 'WORKTREE\t%s\t%s\t%s\tdirty=%s\tunpushed=%s\n' \
			"$main" "$wt" "$wt_branch" "$wt_dirty" "$wt_unpushed"
	done
}

scan_roots() {
	local root gitdir
	for root in "${sync_roots[@]}"; do
		[ -d "$root" ] || { echo "inventory.sh: no such directory: $root" >&2; continue; }
		while IFS= read -r gitdir; do
			scan_repo "$(dirname "$gitdir")"
		done < <(find "$root" -maxdepth 4 -name .git -prune -print 2>/dev/null | sort)
	done
}

[ "$no_tmux" -eq 1 ] || scan_tmux
scan_roots

echo "inventory: agents active=$n_active waiting=$n_waiting idle=$n_idle dead=$n_dead;" \
	"repos with WIP=$n_repos (stale=$n_stale); extra worktrees=$n_worktrees" >&2
