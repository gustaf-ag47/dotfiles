#!/bin/bash
# tests/system-layer.sh -- exercise scripts/install-system.sh without root.
#
# For every profile: apply the files into a throwaway --root, then re-run with
# --check and require "In sync" (idempotency). Spot-checks layering, modes and
# @DOTFILES@ substitution, and validates every packages/services file.
#
# SYSTEM_LAYER_RESOLVE=1 additionally resolves every declared package against
# the live Arch repos (pacman -Si); CI does this inside archlinux:latest as the
# drift canary for system/*/packages.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1
DOTFILES="$PWD"
export DOTFILES
fail=0
ok() { echo "  ok   $*"; }
no() {
	echo "  FAIL $*"
	fail=1
}
check() {
	local desc="$1"
	shift
	if "$@" >/dev/null 2>&1; then ok "$desc"; else no "$desc"; fi
}

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

echo "-- every profile applies cleanly and is idempotent"
for env in profiles/*.env; do
	p="$(basename "$env" .env)"
	root="$tmp/$p"
	mkdir -p "$root"
	if bash scripts/install-system.sh --profile "$p" --root "$root" --apply >"$tmp/$p.log" 2>&1; then
		ok "$p: apply"
	else
		no "$p: apply (see below)"
		sed 's/^/       /' "$tmp/$p.log"
		continue
	fi
	if bash scripts/install-system.sh --profile "$p" --root "$root" --check >"$tmp/$p.check" 2>&1 &&
		grep -q '^In sync\.$' "$tmp/$p.check"; then
		ok "$p: second run is in sync"
	else
		no "$p: second run drifted"
		sed 's/^/       /' "$tmp/$p.check"
	fi
done

echo "-- layering and rendering"
check "common layer reaches every host (logind idle)" \
	test -f "$tmp/skrubben/etc/systemd/logind.conf.d/idle.conf"
check "gpu layer: hybrid arch gets early NVIDIA KMS" \
	grep -q 'nvidia_drm' "$tmp/arch/etc/mkinitcpio.conf.d/nvidia.conf"
check "gpu layer: intel xps14 gets no NVIDIA files" \
	test ! -e "$tmp/xps14/etc/mkinitcpio.conf.d/nvidia.conf"
check "host layer: xps14 blacklists intel_cvs" \
	grep -q '^blacklist intel_cvs' "$tmp/xps14/etc/modprobe.d/intel-cvs-late.conf"
check "host layer: xps14 ships the intel-cvs-late loader (+x)" \
	test -x "$tmp/xps14/usr/local/bin/intel-cvs-late"
check "host layer stays on its host (no xps14 files on arch)" \
	test ! -e "$tmp/arch/etc/modprobe.d/intel-cvs-late.conf"
check "executables keep +x (hyprland-sigstop)" \
	test -x "$tmp/arch/etc/systemd/system-sleep/hyprland-sigstop"
check "plain files are not executable (iwlwifi.conf)" \
	test ! -x "$tmp/arch/etc/modprobe.d/iwlwifi.conf"
check "@DOTFILES@ is substituted" \
	grep -q "ExecStart=$DOTFILES/bin/iwlwifi-watchdog" "$tmp/arch/etc/systemd/system/iwlwifi-watchdog.service"
check "no @DOTFILES@ token survives anywhere" \
	bash -c "! grep -rq '@DOTFILES@' '$tmp'"
check "grub drop-ins append, never replace" \
	bash -c "grep -h GRUB_CMDLINE_LINUX_DEFAULT '$tmp'/*/etc/default/grub.d/*.cfg | grep -v '\${GRUB_CMDLINE_LINUX_DEFAULT} ' | grep -q . && exit 1 || exit 0"
check "dry run never writes" \
	bash -c "mkdir '$tmp/dry' && bash scripts/install-system.sh --profile arch --root '$tmp/dry' >/dev/null && [ -z \"\$(ls -A '$tmp/dry')\" ]"
check "--check exits 1 on drift" \
	bash -c "! bash scripts/install-system.sh --profile arch --root '$tmp/dry' --check >/dev/null"

echo "-- declarations are well formed"
for f in system/*/packages system/*/*/packages system/*/packages.aur system/*/*/packages.aur; do
	[ -f "$f" ] || continue
	bad="$(sed -e 's/#.*//' -e '/^[[:space:]]*$/d' "$f" | grep -vE '^[a-z0-9@._+-]+$' || true)"
	if [ -z "$bad" ]; then ok "$f"; else no "$f: bad package line(s): $bad"; fi
done
for f in system/*/services system/*/*/services; do
	[ -f "$f" ] || continue
	bad="$(sed -e 's/#.*//' -e '/^[[:space:]]*$/d' "$f" |
		grep -vE '^(enable|disable|mask) [A-Za-z0-9@._-]+\.(service|timer|socket|path|target)$' || true)"
	if [ -z "$bad" ]; then ok "$f"; else no "$f: bad service line(s): $bad"; fi
done
for f in system/*/*/user-services; do
	[ -f "$f" ] || continue
	while read -r action unit; do
		case "$action" in enable | disable) ;; *) no "$f: bad line '$action $unit'"; continue ;; esac
		if [ -f "config/systemd/user/$unit" ]; then
			ok "$f: $unit (public)"
		elif [ -f "local/config/systemd/user/$unit" ]; then
			ok "$f: $unit (private overlay)"
		elif [ ! -d local/config ]; then
			ok "$f: $unit (private overlay not present here; not checked)"
		else
			no "$f: no unit file for $unit in config/ or local/config/systemd/user"
		fi
	done < <(sed -e 's/#.*//' -e '/^[[:space:]]*$/d' "$f")
done

# Within one profile, each package should come from exactly one layer (gpu/
# and hosts/ hold alternatives, so duplicates ACROSS profiles are fine).
for env in profiles/*.env; do
	p="$(basename "$env" .env)"
	dups="$(bash scripts/install-system.sh --profile "$p" --list 2>/dev/null |
		sed -n 's/^  \[.\] //p' | sort | uniq -d | tr '\n' ' ')"
	if [ -z "$dups" ]; then ok "$p: no package declared twice"; else no "$p: declared twice: $dups"; fi
done
for env in profiles/*.env; do
	roles="$(bash -c ". '$env'; echo \"\${PROFILE_ROLES:-}\"")"
	for r in $roles; do
		check "$(basename "$env" .env): role '$r' exists" test -d "system/roles/$r"
	done
done

echo "-- review modes"
check "--list prints every layer of xps14" \
	bash -c "bash scripts/install-system.sh --profile xps14 --list | grep -q '^roles/personal/packages.aur'"
check "--list counts packages" \
	bash -c "bash scripts/install-system.sh --profile xps14 --list | grep -qE '^[0-9]+ packages\\.'"
if command -v pacman >/dev/null 2>&1; then
	check "--undeclared runs" bash scripts/install-system.sh --profile arch --undeclared
fi

for d in system/hosts/*/; do
	h="$(basename "$d")"
	check "system/hosts/$h has a matching profiles/$h.env" test -f "profiles/$h.env"
done

if [ "${SYSTEM_LAYER_RESOLVE:-0}" = 1 ]; then
	echo "-- every declared package exists in today's Arch repos"
	while IFS= read -r pkg; do
		if pacman -Si "$pkg" >/dev/null 2>&1; then ok "$pkg"; else no "$pkg not in the repos"; fi
	done < <(cat system/*/packages system/*/*/packages 2>/dev/null |
		sed -e 's/#.*//' -e 's/[[:space:]]*$//' -e '/^[[:space:]]*$/d' | sort -u)

	echo "-- every AUR package exists in the AUR (and is NOT in the official repos)"
	mapfile -t aurpk < <(cat system/*/packages.aur system/*/*/packages.aur 2>/dev/null |
		sed -e 's/#.*//' -e 's/[[:space:]]*$//' -e '/^[[:space:]]*$/d' | sort -u)
	if [ ${#aurpk[@]} -gt 0 ]; then
		q="$(printf 'arg[]=%s&' "${aurpk[@]}")"
		found="$(curl -fsS "https://aur.archlinux.org/rpc/v5/info?${q%&}" |
			python3 -c 'import sys,json;print("\n".join(r["Name"] for r in json.load(sys.stdin)["results"]))')"
		for pkg in "${aurpk[@]}"; do
			if pacman -Si "$pkg" >/dev/null 2>&1; then
				no "$pkg is in the official repos: move it to packages"
			elif printf '%s\n' "$found" | grep -qx "$pkg"; then
				ok "aur: $pkg"
			else
				no "aur: $pkg not found in the AUR"
			fi
		done
	fi
fi

echo
if [ "$fail" -eq 0 ]; then echo "system layer: all checks passed"; else echo "system layer: FAILURES"; fi
exit "$fail"
