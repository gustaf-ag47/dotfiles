#!/bin/bash
# Tests for `bootstrap-kit preflight` -- the terminal/adapter capability check.
#
# This logic used to live inline in install-arch's post_install_user.sh, where
# the only way to exercise it was a ~40 minute VM install. Behind the kit's
# interface it is testable in seconds.
#
# The interesting cases need a pty (or the deliberate absence of one), so the
# harness uses setsid to drop the controlling terminal and `script` to fake one.
set -uo pipefail

KIT="${KIT_BIN:-$(cd "$(dirname "$0")/.." && pwd)/bin/bootstrap-kit}"
pass=0 fail=0
ok() {
	printf '  \033[32mok\033[0m   %s\n' "$1"
	pass=$((pass + 1))
}
no() {
	printf '  \033[31mFAIL\033[0m %s\n' "$1"
	fail=$((fail + 1))
}
check_rc() { # check_rc DESC EXPECTED_RC ACTUAL_RC
	if [ "$2" = "$3" ]; then ok "$1"; else no "$1 (want rc=$2, got rc=$3)"; fi
}

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
export DOTFILES="$WORK"
mkdir -p "$WORK/secrets"

echo "== bootstrap-kit preflight =="

umask 077
age-keygen -o "$WORK/secrets/test-identity.txt" 2>"$WORK/p1"
P1=$(grep -oE 'age1[a-z0-9]+' "$WORK/p1" | head -1)
age-keygen -o "$WORK/secrets/other.txt" 2>"$WORK/p2"
P2=$(grep -oE 'age1[a-z0-9]+' "$WORK/p2" | head -1)
printf '%s a\n%s b\n' "$P1" "$P2" >"$WORK/secrets/recipients.txt"
echo hello >"$WORK/plain.txt"
echo "$WORK/plain.txt x" >"$WORK/secrets/kit-manifest.txt"
"$KIT" build -o "$WORK/kit.age" >/dev/null 2>&1

# --- missing prerequisites -------------------------------------------------
"$KIT" preflight "$WORK/nope.age" >/dev/null 2>&1
check_rc "missing kit is refused" 1 $?

env BOOTSTRAP_FILE_IDENTITY=/nonexistent BOOTSTRAP_YUBIKEY_IDENTITY=/nonexistent \
	"$KIT" preflight "$WORK/kit.age" >/dev/null 2>&1
check_rc "no available adapter is refused" 1 $?

# --- the happy, non-interactive path --------------------------------------
"$KIT" preflight "$WORK/kit.age" >"$WORK/pf.out" 2>&1
check_rc "file adapter passes preflight" 0 $?
if grep -q "interactive: no" "$WORK/pf.out"; then
	ok "file adapter reported as non-interactive"
else
	no "file adapter interactivity misreported"
fi
if grep -q "expect:      no prompts" "$WORK/pf.out"; then
	ok "reports what the human should expect"
else
	no "no expectation line"
fi

# --- it must NOT decrypt ---------------------------------------------------
# A decrypting pre-check costs a PIN prompt and a touch for nothing, because
# restore already stages before placing. Prove preflight works on a kit no
# available identity can open: capability, not decryption.
age -r "$P2" -o "$WORK/foreign.age" "$WORK/plain.txt" 2>/dev/null
env BOOTSTRAP_FILE_IDENTITY="$WORK/secrets/test-identity.txt" \
	"$KIT" preflight "$WORK/foreign.age" >/dev/null 2>&1
check_rc "preflight does not decrypt (passes on an unopenable kit)" 0 $?
if env BOOTSTRAP_FILE_IDENTITY="$WORK/secrets/test-identity.txt" \
	"$KIT" verify "$WORK/foreign.age" >/dev/null 2>&1; then
	no "verify wrongly succeeded on an unopenable kit"
else
	ok "verify (which DOES decrypt) correctly fails on the same kit"
fi

# --- terminal detection ----------------------------------------------------
# /dev/tty exists as a device node even with no controlling terminal, so the
# check has to OPEN it. These two cases are what that distinguishes.
setsid env BOOTSTRAP_ADAPTER=passphrase "$KIT" preflight "$WORK/kit.age" \
	</dev/null >"$WORK/notty.out" 2>&1
check_rc "interactive adapter with NO terminal is refused" 1 $?
if grep -q "no terminal" "$WORK/notty.out"; then
	ok "explains that a terminal is required"
else
	no "unhelpful message when no terminal"
fi

if command -v script >/dev/null 2>&1; then
	script -qec "BOOTSTRAP_ADAPTER=passphrase $KIT preflight $WORK/kit.age" /dev/null \
		>"$WORK/tty.out" 2>&1
	rc=$?
	check_rc "interactive adapter WITH a terminal passes" 0 "$rc"
	if grep -q "passphrase prompt" "$WORK/tty.out"; then
		ok "warns about the passphrase prompt"
	else
		no "no prompt warning"
	fi
else
	echo "  skip script(1) not available"
fi

# --- non-interactive adapters do not need a terminal ----------------------
setsid "$KIT" preflight "$WORK/kit.age" </dev/null >/dev/null 2>&1
check_rc "file adapter passes without a terminal" 0 $?

printf '\n%s passed, %s failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
