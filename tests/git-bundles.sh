#!/bin/bash
# tests/git-bundles.sh -- round trip for bin/git-bundle-backup + bin/git-rehydrate.
#
# Machine A has: a repo with a remote, a pushed main, an unpushed branch, two
# stashes and an uncommitted edit; and a repo with no remote at all. A new
# machine B receives the working trees the way Syncthing delivers them (no
# .git) plus the bundles, and must end up with identical history.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1
BIN="$PWD/bin"
fail=0
ok() { echo "  ok   $*"; }
no() {
	echo "  FAIL $*"
	fail=1
}
check() {
	local d="$1"
	shift
	if "$@" >/dev/null 2>&1; then ok "$d"; else no "$d"; fi
}

T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1
g() { git -c init.defaultBranch=main "$@"; }

# --- machine A ---------------------------------------------------------------
A="$T/a/sync"
mkdir -p "$A/src" "$T/remote"
g init -q --bare "$T/remote/proj.git"
g clone -q "$T/remote/proj.git" "$A/src/proj" 2>/dev/null
(
	cd "$A/src/proj" || exit 1
	echo one >f && g add f && g commit -qm one && g push -q origin main
	g switch -qc feature && echo two >g && g add g && g commit -qm two
	g switch -q main
	echo s1 >>f && g stash -q
	echo s2 >>f && g stash -q
	echo edit >>f # uncommitted, synced by Syncthing
)
mkdir -p "$A/src/solo"
(
	cd "$A/src/solo" || exit 1
	g init -q
	echo a >x && g add x && g commit -qm a
	echo b >>x && g commit -qam b
	echo st >>x && g stash -q
)

want_main="$(git -C "$A/src/proj" rev-parse main)"
want_feat="$(git -C "$A/src/proj" rev-parse feature)"
want_s0="$(git -C "$A/src/proj" rev-parse 'stash@{0}^{tree}')"
want_s1="$(git -C "$A/src/proj" rev-parse 'stash@{1}^{tree}')"
want_solo="$(git -C "$A/src/solo" rev-parse HEAD)"

echo "-- backup on machine A"
out="$(SYNC="$A" GIT_BUNDLE_DIR="$A/archive/git-bundles" "$BIN/git-bundle-backup" 2>&1)"
printf '     %s\n' "${out//$'\n'/$'\n     '}"
host="$(cat /etc/hostname 2>/dev/null || hostname)"
check "manifest written" test -f "$A/archive/git-bundles/$host/repos.tsv"
check "local bundle for the repo with a remote" test -f "$A/archive/git-bundles/$host/src/proj.local.bundle"
check "full bundle for the repo without a remote" test -f "$A/archive/git-bundles/$host/src/solo.full.bundle"
check "no temporary stash refs left behind" \
	bash -c "[ -z \"\$(git -C '$A/src/proj' for-each-ref refs/bundle-stash)\" ]"
out2="$(SYNC="$A" GIT_BUNDLE_DIR="$A/archive/git-bundles" "$BIN/git-bundle-backup" 2>&1)"
check "second run rewrites nothing" bash -c "echo '$out2' | grep -q '0 bundle(s) written, 2 unchanged'"

# --- machine B: what Syncthing delivers (no .git) ------------------------------
B="$T/b/sync"
mkdir -p "$B"
rsync -a --exclude .git "$A/" "$B/"
check "B starts without .git" test ! -e "$B/src/proj/.git"

echo "-- rehydrate on machine B"
SYNC="$B" GIT_BUNDLE_DIR="$B/archive/git-bundles" "$BIN/git-rehydrate" --apply 2>&1 | sed 's/^/     /'
P="$B/src/proj"
check "main matches A" test "$(git -C "$P" rev-parse main)" = "$want_main"
check "unpushed branch restored" test "$(git -C "$P" rev-parse feature 2>/dev/null)" = "$want_feat"
check "on branch main" test "$(git -C "$P" symbolic-ref --short HEAD)" = main
check "upstream tracks origin/main" test "$(git -C "$P" rev-parse --abbrev-ref '@{u}')" = origin/main
check "two stashes, newest first" bash -c "
	[ \"\$(git -C '$P' stash list | wc -l)\" = 2 ] &&
	[ \"\$(git -C '$P' rev-parse 'stash@{0}^{tree}')\" = '$want_s0' ] &&
	[ \"\$(git -C '$P' rev-parse 'stash@{1}^{tree}')\" = '$want_s1' ]"
check "synced uncommitted edit kept as a local change" \
	bash -c "git -C '$P' status --porcelain | grep -q '^ M f' && tail -1 '$P/f' | grep -qx edit"
check "no-remote repo restored from its bundle" test "$(git -C "$B/src/solo" rev-parse HEAD)" = "$want_solo"
check "no-remote repo keeps its stash" test "$(git -C "$B/src/solo" stash list | wc -l)" = 1

echo "-- repos Syncthing never delivered"
C="$T/c/sync"
mkdir -p "$C"
rsync -a --exclude .git --exclude src/proj "$A/" "$C/"
check "dry run without --clone-missing leaves it missing" \
	bash -c "SYNC='$C' GIT_BUNDLE_DIR='$C/archive/git-bundles' '$BIN/git-rehydrate' src/proj | grep -q 'use --clone-missing'"
SYNC="$C" GIT_BUNDLE_DIR="$C/archive/git-bundles" "$BIN/git-rehydrate" --apply --clone-missing src/proj >/dev/null 2>&1
check "--clone-missing clones from the remote" test "$(git -C "$C/src/proj" rev-parse main 2>/dev/null)" = "$want_main"
check "...and restores the unpushed branch" test "$(git -C "$C/src/proj" rev-parse feature 2>/dev/null)" = "$want_feat"

echo
if [ "$fail" -eq 0 ]; then echo "git bundles: all checks passed"; else echo "git bundles: FAILURES"; fi
exit "$fail"
