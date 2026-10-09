#!/usr/bin/env bash
set -euo pipefail

# Resolve machine facts from machines.conf (see that file for the format).
#
# Usage:
#   machines.sh list                 -> one machine name per line
#   machines.sh get <name>           -> every key=value of that machine
#   machines.sh get <name> <key>     -> that value only
#
# Config: $MACHINE_HANDOFF_CONF, else $LOCAL_CONFIG/machine-handoff/machines.conf
# (the private overlay; seed it from ../machines.conf.example -- the real
# registry holds hostnames, users and paths that must stay out of git).
# Exit codes: 2 usage, 3 missing config, 4 unknown machine, 5 unknown key.

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
local_config="${LOCAL_CONFIG:-${HOME:-}/sync/state/dotfiles-local}"
conf="${MACHINE_HANDOFF_CONF:-$local_config/machine-handoff/machines.conf}"

usage() {
	cat <<'EOF'
Usage: machines.sh list                 -> one machine name per line
       machines.sh get <name>           -> every key=value of that machine
       machines.sh get <name> <key>     -> that value only

Config: $MACHINE_HANDOFF_CONF, else $LOCAL_CONFIG/machine-handoff/machines.conf
(private overlay; seed from machines.conf.example next to this skill).
Exit codes: 2 usage, 3 missing config, 4 unknown machine, 5 unknown key.
EOF
}

[ -f "$conf" ] || {
	echo "machines.sh: config not found: $conf" >&2
	echo "machines.sh: seed it from $script_dir/../machines.conf.example" >&2
	exit 3
}

# Parse the ini once into parallel arrays.
machines=()
declare -A values=()
section=""
while IFS= read -r line; do
	line="${line%%#*}"
	line="${line#"${line%%[![:space:]]*}"}"
	line="${line%"${line##*[![:space:]]}"}"
	[ -z "$line" ] && continue
	case "$line" in
	\[*\])
		section="${line#\[}"
		section="${section%\]}"
		machines+=("$section")
		;;
	*=*)
		[ -n "$section" ] || {
			echo "machines.sh: key outside a [machine] section: $line" >&2
			exit 3
		}
		values["$section/${line%%=*}"]="${line#*=}"
		;;
	*)
		echo "machines.sh: unparseable line in $conf: $line" >&2
		exit 3
		;;
	esac
done <"$conf"

require_machine() {
	local name="$1" m
	for m in "${machines[@]}"; do
		[ "$m" = "$name" ] && return 0
	done
	echo "machines.sh: unknown machine '$name' (known: ${machines[*]})" >&2
	exit 4
}

case "${1:-}" in
list)
	printf '%s\n' "${machines[@]}"
	;;
get)
	name="${2:-}"
	[ -n "$name" ] || { usage >&2; exit 2; }
	require_machine "$name"
	if [ $# -ge 3 ]; then
		key="$name/$3"
		[ -n "${values[$key]:-}" ] || {
			echo "machines.sh: machine '$name' has no key '$3'" >&2
			exit 5
		}
		printf '%s\n' "${values[$key]}"
	else
		for k in "${!values[@]}"; do
			case "$k" in
			"$name"/*) printf '%s=%s\n' "${k#"$name"/}" "${values[$k]}" ;;
			esac
		done | sort
	fi
	;;
-h | --help)
	usage
	;;
*)
	usage >&2
	exit 2
	;;
esac
