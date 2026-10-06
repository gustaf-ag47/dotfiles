#!/bin/bash
# install-system.sh -- apply the root-owned system layer (system/) for a machine.
#
# scripts/install.sh links user config; this is its root-side counterpart:
# packages, /etc files, kernel parameters, services and DKMS sources that used
# to be hand-made per machine and documented only in CLAUDE.md.
#
# Layers, applied in order (a later layer wins for the same destination path):
#   system/common/            every machine
#   system/roles/<role>/      each role in PROFILE_ROLES, in order
#   system/gpu/<PROFILE_GPU>/ intel | hybrid | nvidia
#   system/hosts/<profile>/   this machine only
# Each layer may hold:
#   packages      one pacman package per line ('#' comments)
#   packages.aur  AUR packages, built with paru as the invoking (sudo) user
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
#   scripts/install-system.sh --profile xps14 --list   # review its packages
#   scripts/install-system.sh --undeclared    # installed here, declared nowhere
#
# See system/README.md.
set -euo pipefail

DOTFILES="${DOTFILES:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SYSTEM_DIR="$DOTFILES/system"

# Run from / so the hooks never inherit a deleted working directory. install-arch
# once called this from ~/dotfiles, which `make install` had just moved away:
# mkinitcpio's pushd and dkms's `cd -` both failed on the dangling cwd.
cd / || exit 1

APPLY=0
CHECK=0
MODE=plan # plan | list | undeclared
ROOT=/
PROFILE="${PROFILE:-}"

usage() { sed -n '2,/^set -euo/{/^set -euo/d;s/^# \{0,1\}//;p}' "$0"; }

while [ $# -gt 0 ]; do
	case "$1" in
	--apply) APPLY=1 ;;
	--check) CHECK=1 ;;
	--list) MODE=list ;;
	--undeclared) MODE=undeclared ;;
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
PROFILE_ROLES="${PROFILE_ROLES:-}"

layers=("$SYSTEM_DIR/common")
for r in $PROFILE_ROLES; do
	if [ -d "$SYSTEM_DIR/roles/$r" ]; then
		layers+=("$SYSTEM_DIR/roles/$r")
	else
		echo "error: profile $PROFILE names role '$r' but system/roles/$r does not exist" >&2
		exit 1
	fi
done
if [ -n "$PROFILE_GPU" ]; then
	if [ -d "$SYSTEM_DIR/gpu/$PROFILE_GPU" ]; then
		layers+=("$SYSTEM_DIR/gpu/$PROFILE_GPU")
	else
		echo "warning: no system/gpu/$PROFILE_GPU layer" >&2
	fi
fi
[ -d "$SYSTEM_DIR/hosts/$PROFILE" ] && layers+=("$SYSTEM_DIR/hosts/$PROFILE")

list_entries() { # strip comments and blank lines
	[ -f "$1" ] || return 0
	sed -e 's/#.*//' -e 's/[[:space:]]*$//' -e '/^[[:space:]]*$/d' "$1"
}

is_installed() { command -v pacman >/dev/null 2>&1 && pacman -Q "$1" >/dev/null 2>&1; }

# --- review modes (read-only, no root) ----------------------------------------
if [ "$MODE" = list ]; then
	echo "Packages for profile $PROFILE (roles: ${PROFILE_ROLES:-none}, gpu: ${PROFILE_GPU:-none})"
	echo "  [x] installed on THIS machine   [ ] not installed here"
	total=0
	for l in "${layers[@]}"; do
		for kind in packages packages.aur; do
			mapfile -t pk < <(list_entries "$l/$kind")
			[ ${#pk[@]} -gt 0 ] || continue
			total=$((total + ${#pk[@]}))
			echo
			printf '%s/%s (%d)\n' "${l#"$SYSTEM_DIR/"}" "$kind" "${#pk[@]}"
			head -1 "$l/$kind" | grep '^#' | sed 's/^/  /' || true
			for p in "${pk[@]}"; do
				if is_installed "$p"; then printf '  [x] %s\n' "$p"; else printf '  [ ] %s\n' "$p"; fi
			done
		done
	done
	echo
	echo "$total packages. Edit system/roles/<role>/packages*, or PROFILE_ROLES in profiles/$PROFILE.env."
	exit 0
fi

if [ "$MODE" = undeclared ]; then
	command -v pacman >/dev/null 2>&1 || { echo "needs pacman" >&2; exit 1; }
	declared="$(for l in "${layers[@]}"; do list_entries "$l/packages"; list_entries "$l/packages.aur"; done | sort -u)"
	mapfile -t extra < <(comm -23 <(pacman -Qeq | sort) <(printf '%s\n' "$declared"))
	echo "Explicitly installed on this machine but declared by no layer of profile $PROFILE:"
	if [ ${#extra[@]} -eq 0 ]; then
		echo "  (none)"
	else
		for p in "${extra[@]}"; do
			if pacman -Qmq "$p" >/dev/null 2>&1; then echo "  $p (AUR/foreign)"; else echo "  $p"; fi
		done
		echo
		echo "${#extra[@]} package(s). Add each to a role or host, or remove it (pacman -Rns)."
	fi
	exit 0
fi

mode_word="dry run"
[ "$APPLY" -eq 1 ] && mode_word="apply"
echo "System layer: profile=$PROFILE roles=${PROFILE_ROLES:-none} gpu=${PROFILE_GPU:-none} root=${ROOT:-/} ($mode_word)"
for l in "${layers[@]}"; do echo "  layer: ${l#"$DOTFILES/"}"; done

drift=0
failures=0
run() {
	# Print a command; execute it only when applying to the live system. A
	# failure is reported and counted, not fatal: one bad hook (say, a DKMS
	# build) must not leave the rest of the layer unapplied.
	echo "    + $*"
	if [ "$APPLY" -eq 1 ] && [ "$LIVE" -eq 1 ]; then
		if ! "$@"; then
			echo "    ! failed: $*" >&2
			failures=$((failures + 1))
		fi
	fi
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
		echo "   missing: ${missing[*]}"
		if [ "$APPLY" -eq 1 ]; then
			# One transaction is fast; if it fails (one renamed package aborts
			# the whole thing), fall back to one at a time so the rest land.
			if ! pacman -S --needed --noconfirm "${missing[@]}"; then
				echo "    ! batch install failed, retrying one by one" >&2
				for p in "${missing[@]}"; do run pacman -S --needed --noconfirm "$p"; done
			fi
		else
			echo "    + pacman -S --needed --noconfirm <${#missing[@]} packages>"
		fi
	else
		echo "   (fake root, not installed): ${missing[*]}"
	fi
fi

# --- AUR packages ------------------------------------------------------------
aur=()
for l in "${layers[@]}"; do
	while IFS= read -r p; do aur+=("$p"); done < <(list_entries "$l/packages.aur")
done
echo "-- AUR packages (${#aur[@]} declared)"
if [ ${#aur[@]} -gt 0 ]; then
	aur_missing=()
	if [ "$LIVE" -eq 1 ] && command -v pacman >/dev/null 2>&1; then
		for p in "${aur[@]}"; do is_installed "$p" || aur_missing+=("$p"); done
	else
		aur_missing=("${aur[@]}")
	fi
	if [ ${#aur_missing[@]} -eq 0 ]; then
		echo "   all installed"
	elif [ "$LIVE" -eq 0 ]; then
		echo "   (fake root, not installed): ${aur_missing[*]}"
	else
		drift=$((drift + 1))
		echo "   missing: ${aur_missing[*]}"
		# makepkg refuses to run as root: build as the user who invoked sudo.
		aur_user="${SUDO_USER:-}"
		if [ -z "$aur_user" ] || [ "$aur_user" = root ] || ! command -v paru >/dev/null 2>&1; then
			echo "   cannot build AUR packages here (need paru and sudo from a normal user);"
			echo "   run as that user: paru -S --needed ${aur_missing[*]}"
		else
			for p in "${aur_missing[@]}"; do
				run sudo -u "$aur_user" paru -S --needed --noconfirm --skipreview "$p"
			done
		fi
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
	# `add` registers the source (no headers needed) so dkms's pacman hook
	# builds it whenever headers arrive; `install` only if they are here now.
	if [ "$LIVE" -eq 0 ] || ! dkms status -m "${dir%-*}" -v "${dir##*-}" 2>/dev/null | grep -q .; then
		run dkms add -m "${dir%-*}" -v "${dir##*-}"
	fi
	if [ "$LIVE" -eq 0 ] || [ -d "/usr/lib/modules/$(uname -r)/build" ]; then
		run dkms install -m "${dir%-*}" -v "${dir##*-}"
	else
		echo "   no headers for $(uname -r): ${dir%-*} will build when they are installed"
	fi
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
if [ "$failures" -gt 0 ]; then
	echo "$failures command(s) FAILED (see above). Fix and re-run with --apply."
	exit 1
elif [ "$drift" -eq 0 ]; then
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
