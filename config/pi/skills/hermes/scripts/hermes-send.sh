#!/usr/bin/env bash
set -euo pipefail

usage() {
	cat <<'EOF'
Usage: hermes-send.sh [--target SESSION:WINDOW] [--mode auto|queue|steer|interrupt] MESSAGE...
       hermes-send.sh [--target SESSION:WINDOW] --where
       hermes-send.sh [--target SESSION:WINDOW] --tail [N]
       hermes-send.sh [--target SESSION:WINDOW] --state

Sends one single-line message to the Hermes Agent CLI running in tmux.
Target: --target, else $HERMES_TMUX_TARGET, else the one window named "hermes".
Mode auto queues the message when Hermes is busy, because a plain message to a
busy Hermes interrupts its current run (busy_input_mode: interrupt).
EOF
}

target="${HERMES_TMUX_TARGET:-}"
mode=auto
action=send
tail_lines=15

while [ $# -gt 0 ]; do
	case "$1" in
	--target) target="$2"; shift 2 ;;
	--mode) mode="$2"; shift 2 ;;
	--where) action=where; shift ;;
	--state) action=state; shift ;;
	--tail)
		action="tail"
		shift
		if [ $# -gt 0 ] && [[ "$1" =~ ^[0-9]+$ ]]; then tail_lines="$1"; shift; fi
		;;
	-h | --help) usage; exit 0 ;;
	--) shift; break ;;
	-*) echo "hermes-send: unknown option $1" >&2; usage >&2; exit 2 ;;
	*) break ;;
	esac
done

resolve_target() {
	if [ -n "$target" ]; then
		case "$target" in
		%* | *:[0-9] | *:[0-9][0-9] | *.[0-9]*)
			echo "hermes-send: address Hermes by session:window-name, not '$target'" >&2
			exit 3
			;;
		esac
		tmux list-windows -a -F '#{session_name}:#{window_name}' | grep -qxF "$target" || {
			echo "hermes-send: no tmux window '$target'" >&2
			exit 4
		}
		return
	fi
	local matches
	matches=$(tmux list-windows -a -F '#{session_name}:#{window_name}' | grep -E ':hermes$' || true)
	case "$(printf '%s\n' "$matches" | grep -c .)" in
	1) target="$matches" ;;
	0) echo "hermes-send: no window named 'hermes'; set HERMES_TMUX_TARGET or pass --target" >&2; exit 4 ;;
	*) echo "hermes-send: several windows named 'hermes': $(echo "$matches" | tr '\n' ' ')- pass --target" >&2; exit 4 ;;
	esac
	local panes
	panes=$(tmux list-panes -t "$target" -F x | wc -l)
	[ "$panes" -eq 1 ] || { echo "hermes-send: '$target' has $panes panes; Hermes needs a single-pane window" >&2; exit 4; }
}

pane_text() {
	tmux capture-pane -p -t "$target" | grep -v '^[[:space:]]*$' | tail -n "$1"
}

hermes_state() {
	if pane_text 6 | grep -qE 'Ctrl\+C cancel|Working|thinking'; then echo busy; else echo idle; fi
}

resolve_target

case "$action" in
where) echo "$target"; exit 0 ;;
state) hermes_state; exit 0 ;;
tail) pane_text "$tail_lines"; exit 0 ;;
esac

[ $# -gt 0 ] || { usage >&2; exit 2; }
message="$*"
case "$message" in
*$'\n'*) echo "hermes-send: message must be one line; a newline submits early" >&2; exit 2 ;;
esac

state=$(hermes_state)
prefix=""
case "$mode" in
auto) [ "$state" = busy ] && prefix="/queue " ;;
queue) prefix="/queue " ;;
steer) prefix="/steer " ;;
interrupt) prefix="" ;;
*) echo "hermes-send: unknown mode $mode" >&2; exit 2 ;;
esac

tmux send-keys -t "$target" -l "${prefix}${message}"
sleep 0.5
tmux send-keys -t "$target" Enter
sleep 2

delivered=queued
[ -z "$prefix" ] && delivered=sent
[ "$prefix" = "/steer " ] && delivered=steered
echo "hermes-send: $delivered to $target (Hermes was $state)"
