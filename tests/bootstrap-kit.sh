#!/bin/bash
# Round-trip tests for bin/bootstrap-kit.
#
# Uses SYNTHETIC secrets only -- never touches the real ~/.ssh, ~/cctoken or
# Syncthing identity, and never builds a kit that could be committed.
#
# Proves the ports-and-adapters property that matters: the SAME ciphertext
# opens with either enrolled identity, so swapping the fake adapter for a
# YubiKey later requires no re-encryption and no code change.
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

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
export DOTFILES="$WORK"
mkdir -p "$WORK/secrets" "$WORK/src"

echo "== bootstrap-kit round trip (synthetic secrets) =="

# --- two independent identities: "primary" and "backup" -------------------
umask 077
age-keygen -o "$WORK/secrets/test-identity.txt" 2>"$WORK/p1"
age-keygen -o "$WORK/secrets/test-backup-identity.txt" 2>"$WORK/p2"
age-keygen -o "$WORK/secrets/stranger.txt" 2>"$WORK/p3"
P1=$(grep -oE 'age1[a-z0-9]+' "$WORK/p1" | head -1)
P2=$(grep -oE 'age1[a-z0-9]+' "$WORK/p2" | head -1)
printf '%s primary\n%s backup\n' "$P1" "$P2" >"$WORK/secrets/recipients.txt"

# --- synthetic material with meaningful permissions -----------------------
mkdir -p "$WORK/src/ssh"
echo "PRIVATE-KEY-CONTENT" >"$WORK/src/ssh/id_ed25519"
chmod 600 "$WORK/src/ssh/id_ed25519"
echo "sk-ant-oat01-SYNTHETIC-NOT-A-REAL-TOKEN" >"$WORK/src/cctoken"
chmod 600 "$WORK/src/cctoken"
echo "<configuration><device id=synthetic/></configuration>" >"$WORK/src/config.xml"

cat >"$WORK/secrets/kit-manifest.txt" <<EOF
$WORK/src/ssh        ssh
$WORK/src/cctoken    cctoken
$WORK/src/config.xml syncthing/config.xml
$WORK/src/nonexistent absent/file
EOF

# --- build ----------------------------------------------------------------
if "$KIT" build -o "$WORK/kit.age" >"$WORK/build.log" 2>&1; then
	ok "build succeeds"
else
	no "build failed"
	cat "$WORK/build.log"
fi
if [ -s "$WORK/kit.age" ]; then
	ok "kit is non-empty"
else
	no "kit missing/empty"
fi
if grep -q "skip (absent)" "$WORK/build.log"; then
	ok "absent manifest entry skipped, not fatal"
else
	no "absent entry not handled"
fi

# ciphertext must not contain the plaintext
if grep -qa "SYNTHETIC-NOT-A-REAL-TOKEN" "$WORK/kit.age"; then
	no "SECRET LEAKED IN CIPHERTEXT"
else
	ok "plaintext absent from ciphertext"
fi

# --- unlock with the primary (fake) adapter -------------------------------
env BOOTSTRAP_ADAPTER=file "$KIT" unlock "$WORK/kit.age" "$WORK/out1" >/dev/null 2>&1
if [ -f "$WORK/out1/cctoken" ] && grep -q SYNTHETIC "$WORK/out1/cctoken"; then
	ok "primary adapter unlocks, contents intact"
else
	no "primary adapter unlock failed"
fi
if [ -f "$WORK/out1/ssh/id_ed25519" ]; then
	ok "nested directory restored"
else
	no "nested dir missing"
fi
if [ -f "$WORK/out1/syncthing/config.xml" ]; then
	ok "renamed path restored"
else
	no "renamed path missing"
fi

# permissions are load-bearing: ssh refuses a world-readable key
mode=$(stat -c %a "$WORK/out1/ssh/id_ed25519" 2>/dev/null)
if [ "$mode" = "600" ]; then
	ok "file mode preserved (0600)"
else
	no "mode not preserved (got ${mode:-none})"
fi

# --- THE ports-and-adapters property --------------------------------------
# Same ciphertext, different identity. This is what makes swapping the fake
# adapter for a YubiKey a no-op: no re-encryption, no code change.
BOOTSTRAP_FILE_IDENTITY="$WORK/secrets/test-backup-identity.txt" \
	env BOOTSTRAP_ADAPTER=file "$KIT" unlock "$WORK/kit.age" "$WORK/out2" >/dev/null 2>&1
if [ -f "$WORK/out2/cctoken" ]; then
	ok "BACKUP identity opens the same ciphertext (key loss survivable)"
else
	no "backup identity could not decrypt -- multi-recipient broken"
fi

# --- negative test: an unenrolled identity must NOT decrypt ---------------
if BOOTSTRAP_FILE_IDENTITY="$WORK/secrets/stranger.txt" \
	env BOOTSTRAP_ADAPTER=file "$KIT" verify "$WORK/kit.age" >/dev/null 2>&1; then
	no "SECURITY: an unenrolled identity decrypted the kit"
else
	ok "unenrolled identity correctly refused"
fi

# --- verify subcommand ----------------------------------------------------
if env BOOTSTRAP_ADAPTER=file "$KIT" verify "$WORK/kit.age" >/dev/null 2>&1; then
	ok "verify reports success for an enrolled adapter"
else
	no "verify failed for an enrolled adapter"
fi

# --- guard: refuse a single recipient -------------------------------------
printf '%s only\n' "$P1" >"$WORK/secrets/recipients.txt"
if "$KIT" build -o "$WORK/kit2.age" >"$WORK/b2.log" 2>&1; then
	no "built with a single recipient (should refuse)"
else
	if grep -q "single recipient" "$WORK/b2.log"; then
		ok "refuses to build with one recipient"
	else
		no "failed for the wrong reason"
	fi
fi

printf '\n%s passed, %s failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
