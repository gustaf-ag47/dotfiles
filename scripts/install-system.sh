#!/bin/bash
# install-system.sh -- apply the root-owned system layer (system/) for a machine.
#
# scripts/install.sh links user config; this is its root-side counterpart:
# packages, /etc files, kernel parameters, services and DKMS sources that used
# to be hand-made per machine and documented only in CLAUDE.md.
#
# Layers, applied in order (a later layer wins for the same destination path):
#   system/common/            every machine
#   system/gpu/<PROFILE_GPU>/ intel | hybrid | nvidia
#   system/hosts/<profile>/   this machine only
# Each layer may hold:
#   packages   one pacman package per line ('#' comments)
#   services   "<enable|disable|mask> <unit>" per line
#   files/     a tree mirrored onto /. Mode comes from the repo (+x -> 0755,
#              else 0644). The token @DOTFILES@ is replaced with the repo path.
#
# Default is a DRY RUN that prints the drift. Nothing changes without --apply.
#
# Usage:
#   scripts/install-system.sh                 # show what would change
#   scripts/install-system.sh --check         # same, exit 1 if anything drifted
#   sudo scripts/install-system.sh --apply    # make it so
#   scripts/install-system.sh --apply --root /tmp/r   # files only, into a fake root
#   PROFILE=xps14 scripts/install-system.sh   # another machine's plan
#
# See system/README.md.
set -euo pipefail

DOTFILES="${DOTFILES:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SYSTEM_DIR="$DOTFILES/system"

APPLY=0
CHECK=0
ROOT=/
PROFILE="${PROFILE:-}"

usage() { sed -n '2,/^set -euo/{/^set -euo/d;s/^# \{0,1\}//;p}' "$0"; }

while [ $# -gt 0 ]; do
	case "$1" in
	--apply) APPLY=1 ;;
	--check) CHECK=1 ;;
	--root)
		ROOT="${2:?--root needs a directory}"
		shift
		;;
	--profile)
		PROFILE="${2:?--profile needs a name}"
		shift
		;;
	-h | --help)
		usage
		exit 0
		;;
	*)
		echo "unknown argument: $1" >&2
		usage >&2
		exit 2
		;;
	esac
	shift
done

ROOT="${ROOT%/}"
LIVE=0
[ -z "$ROOT" ] && LIVE=1 # --root / (the default) means the running system

if [ "$APPLY" -eq 1 ] && [ "$LIVE" -eq 1 ] && [ "$(id -u)" -ne 0 ]; then
	echo "error: --apply on the live system needs root (sudo $0 --apply)" >&2
	exit 1
fi

# --- profile (same resolution as scripts/install.sh) -------------------------
if [ -z "$PROFILE" ]; then
	PROFILE="$(cat /etc/hostname 2>/dev/null || hostname 2>/dev/null || echo unknown)"
fi
PROFILE_FILE="$DOTFILES/profiles/$PROFILE.env"
if [ ! -f "$PROFILE_FILE" ]; then
	echo "warning: no profiles/$PROFILE.env, using profiles/default.env" >&2
	PROFILE_FILE="$DOTFILES/profiles/default.env"
fi
# shellcheck disable=SC1090  # path is computed at runtime
. "$PROFILE_FILE"
PROFILE_GPU="${PROFILE_GPU:-}"

layers=("$SYSTEM_DIR/common")
if [ -n "$PROFILE_GPU" ]; then
	if [ -d "$SYSTEM_DIR/gpu/$PROFILE_GPU" ]; then
		layers+=("$SYSTEM_DIR/gpu/$PROFILE_GPU")
	else
		echo "warning: no system/gpu/$PROFILE_GPU layer" >&2
	fi
fi
[ -d "$SYSTEM_DIR/hosts/$PROFILE" ] && layers+=("$SYSTEM_DIR/hosts/$PROFILE")

mode_word="dry run"
[ "$APPLY" -eq 1 ] && mode_word="apply"
echo "System layer: profile=$PROFILE gpu=${PROFILE_GPU:-none} root=${ROOT:-/} ($mode_word)"
for l in "${layers[@]}"; do echo "  layer: ${l#"$DOTFILES/"}"; done

drift=0
run() {
	# Print a command; execute it only when applying to the live system.
	echo "    + $*"
	if [ "$APPLY" -eq 1 ] && [ "$LIVE" -eq 1 ]; then
		"$@"
	fi
}

list_entries() { # strip comments and blank lines
	[ -f "$1" ] || return 0
	sed -e 's/#.*//' -e 's/[[:space:]]*$//' -e '/^[[:space:]]*$/d' "$1"
}

# --- packages ----------------------------------------------------------------
packages=()
for l in "${layers[@]}"; do
	while IFS= read -r p; do packages+=("$p"); done < <(list_entries "$l/packages")
done

echo "-- packages (${#packages[@]} declared)"
if [ ${#packages[@]} -gt 0 ]; then
	missing=()
	if command -v pacman >/dev/null 2>&1 && [ "$LIVE" -eq 1 ]; then
		for p in "${packages[@]}"; do
			pacman -Q "$p" >/dev/null 2>&1 || missing+=("$p")
		done
	else
		missing=("${packages[@]}") # cannot query a fake root: report all
	fi
	if [ ${#missing[@]} -eq 0 ]; then
		echo "   all installed"
	elif [ "$LIVE" -eq 1 ]; then
		drift=$((drift + 1))
		run pacman -S --needed --noconfirm "${missing[@]}"
	else
		echo "   (fake root, not installed): ${missing[*]}"
	fi
fi

# --- files -------------------------------------------------------------------
# Later layers win: build dest -> source with the last writer kept.
declare -A file_src=()
dest_order=()
for l in "${layers[@]}"; do
	[ -d "$l/files" ] || continue
	while IFS= read -r -d '' src; do
		rel="${src#"$l/files/"}"
		[ -n "${file_src[$rel]+x}" ] || dest_order+=("$rel")
		file_src[$rel]="$src"
	done < <(find "$l/files" -type f -print0 | sort -z)
done

stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT

changed=()
echo "-- files (${#dest_order[@]} managed)"
for rel in "${dest_order[@]}"; do
	src="${file_src[$rel]}"
	dest="$ROOT/$rel"
	mode=0644
	[ -x "$src" ] && mode=0755

	rendered="$stage/$(printf '%s' "$rel" | tr '/' '_')"
	sed "s#@DOTFILES@#$DOTFILES#g" "$src" >"$rendered"

	if [ -f "$dest" ] && cmp -s "$rendered" "$dest"; then
		cur_mode="$(stat -c %a "$dest")"
		[ "$cur_mode" = "${mode#0}" ] && continue
		echo "   mode $cur_mode -> ${mode#0}  /$rel"
	elif [ -e "$dest" ]; then
		echo "   update  /$rel"
		diff -u "$dest" "$rendered" | sed -n '3,40s/^/      /p' || true
	else
		echo "   create  /$rel"
	fi
	changed+=("$rel")
	drift=$((drift + 1))

	if [ "$APPLY" -eq 1 ]; then
		if [ "$LIVE" -eq 1 ]; then
			install -D -m "$mode" -o root -g root "$rendered" "$dest"
		else
			install -D -m "$mode" "$rendered" "$dest"
		fi
	fi
done
[ ${#changed[@]} -eq 0 ] && echo "   all up to date"

changed_under() { # changed_under <prefix> -> true if any changed path matches
	local c
	for c in "${changed[@]+"${changed[@]}"}"; do
		case "$c" in "$1"*) return 0 ;; esac
	done
	return 1
}

# --- services ----------------------------------------------------------------
service_lines=()
for l in "${layers[@]}"; do
	while IFS= read -r s; do service_lines+=("$s"); done < <(list_entries "$l/services")
done

echo "-- services (${#service_lines[@]} declared)"
if changed_under etc/systemd/; then
	run systemctl daemon-reload
fi
for line in "${service_lines[@]+"${service_lines[@]}"}"; do
	read -r action unit <<<"$line"
	case "$action" in
	enable) want=enabled ;;
	disable) want=disabled ;;
	mask) want=masked ;;
	*)
		echo "error: bad services line: $line" >&2
		exit 1
		;;
	esac
	if [ "$LIVE" -eq 1 ] && command -v systemctl >/dev/null 2>&1; then
		state="$(systemctl is-enabled "$unit" 2>/dev/null || true)"
		# A unit that does not exist is as disabled as it gets.
		if [ "$want" = disabled ] && { [ "$state" = disabled ] || [ -z "$state" ] || [ "$state" = not-found ]; }; then
			continue
		fi
		[ "$state" = "$want" ] && continue
		drift=$((drift + 1))
		echo "   $unit: ${state:-not-found} -> $want"
		run systemctl "$action" "$unit"
	else
		echo "   (fake root) would $action $unit"
	fi
done

# --- rebuild hooks -----------------------------------------------------------
echo "-- hooks"
hooks=0
if changed_under etc/udev/rules.d/; then
	run udevadm control --reload
	hooks=1
fi
# DKMS sources: usr/src/<name>-<version>/dkms.conf
for rel in "${changed[@]+"${changed[@]}"}"; do
	case "$rel" in usr/src/*/dkms.conf) ;; *) continue ;; esac
	dir="${rel#usr/src/}"
	dir="${dir%/dkms.conf}"
	run dkms install "${dir%-*}/${dir##*-}"
	hooks=1
done
if changed_under etc/modprobe.d/ || changed_under etc/mkinitcpio.conf.d/; then
	run mkinitcpio -P
	hooks=1
fi
if changed_under etc/default/grub.d/; then
	if [ "$LIVE" -eq 0 ] || [ -d /boot/grub ]; then
		run grub-mkconfig -o /boot/grub/grub.cfg
	else
		echo "   kernel parameters changed but /boot/grub is absent: update your bootloader by hand"
	fi
	hooks=1
fi
[ "$hooks" -eq 0 ] && echo "   none needed"

echo
if [ "$drift" -eq 0 ]; then
	echo "In sync."
elif [ "$APPLY" -eq 1 ]; then
	echo "Applied $drift change(s). Reboot if kernel parameters or modules changed."
else
	echo "$drift change(s) pending. Apply with: sudo $0 --apply"
fi

if [ "$CHECK" -eq 1 ] && [ "$APPLY" -eq 0 ] && [ "$drift" -gt 0 ]; then
	exit 1
fi
exit 0
