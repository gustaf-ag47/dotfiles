#!/bin/bash
set -euo pipefail

MERGE_LOG="${PI_DELEGATE_MERGE_LOG:-$HOME/.pi/agent/merge-log.tsv}"
BRIEF="${PI_DELEGATE_BRIEF:-}"
DRY_RUN=0
PR_NUMBER=""
GH_ARGS=()
HAS_METHOD_FLAG=0

die() {
	echo "merge-pr: error: $*" >&2
	exit 1
}

while [ "$#" -gt 0 ]; do
	case "$1" in
	--brief)
		BRIEF="${2:?--brief needs a file}"
		shift 2
		;;
	--dry-run)
		DRY_RUN=1
		shift
		;;
	--squash | --merge | --rebase)
		HAS_METHOD_FLAG=1
		GH_ARGS+=("$1")
		shift
		;;
	-h | --help)
		sed -n '2,20p' "$0"
		exit 0
		;;
	*)
		if [ -z "$PR_NUMBER" ] && [[ "$1" =~ ^[0-9]+$ ]]; then
			PR_NUMBER="$1"
		else
			GH_ARGS+=("$1")
		fi
		shift
		;;
	esac
done

[ -n "$PR_NUMBER" ] || die "need a PR number, e.g. merge-pr.sh 3513"
command -v gh >/dev/null 2>&1 || die "gh not in PATH"

if [ -n "$BRIEF" ]; then
	[ -f "$BRIEF" ] || die "brief not found: $BRIEF"
	# Match an explicit standalone hold, not conditional CI/base safety prose,
	# quoted examples, or a directive for a different PR.
	if python3 - "$BRIEF" "$PR_NUMBER" <<-'PY'
	import re, sys
	from pathlib import Path
	directive = re.compile(
	    r"^(?:[-*+]\s+|\d+[.)]\s+)?(?:merge(?: ownership)?:\s*)?"
	    r"(?:do not merge|don['’]t merge|no[- ]merge)"
	    r"(?:\s+(?:(?:this|the) (?:pr|pull request)|(?:pr|pull request)\s*#?(?P<number>\d+)))?"
	    r"\s*(?:[.!]|\s*[:—–]\s+.+|\s+-\s+.+)?$", re.I)
	fence = None
	for raw in Path(sys.argv[1]).read_text().splitlines():
	    line = raw.strip()
	    marker = re.match(r"^(`{3,}|~{3,})", line)
	    if marker:
	        if fence is None:
	            fence = marker[1][0]
	        elif marker[1][0] == fence:
	            fence = None
	        continue
	    if fence is not None or line.startswith(">"):
	        continue
	    line = line.replace("**", "").replace("__", "").replace("`", "")
	    match = directive.fullmatch(line)
	    if match and (match["number"] is None or int(match["number"]) == int(sys.argv[2])):
	        sys.exit(0)
	sys.exit(3)
	PY
	then
		echo "merge-pr: refused: brief $BRIEF explicitly holds PR #$PR_NUMBER" >&2
		exit 2
	else
		guard_status=$?
		[ "$guard_status" = 3 ] || die "could not parse merge directives in $BRIEF"
	fi
fi

repo_args=()
for ((i = 0; i < ${#GH_ARGS[@]}; i++)); do
	if [ "${GH_ARGS[i]}" = "--repo" ] && [ $((i + 1)) -lt "${#GH_ARGS[@]}" ]; then
		repo_args=(--repo "${GH_ARGS[i + 1]}")
		break
	fi
done

pr_json="$(gh pr view "$PR_NUMBER" "${repo_args[@]}" --json headRefOid,state 2>&1)" ||
	die "gh pr view $PR_NUMBER failed: $pr_json"

pr_state="$(printf '%s' "$pr_json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["state"])')"
if [ "$pr_state" = "MERGED" ]; then
	echo "merge-pr: refused: PR #$PR_NUMBER is already merged; not logging another merge" >&2
	exit 5
fi

head_sha="$(printf '%s' "$pr_json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["headRefOid"])')"

if [ "$HAS_METHOD_FLAG" = 0 ]; then
	GH_ARGS+=(--squash)
fi

if [ "$DRY_RUN" = 1 ]; then
	echo "merge-pr: dry-run OK: would merge PR #$PR_NUMBER (gh pr merge $PR_NUMBER ${GH_ARGS[*]})"
	echo "merge-pr: dry-run: not logging, not merging"
	exit 0
fi

gh pr merge "$PR_NUMBER" "${GH_ARGS[@]}" || die "gh pr merge $PR_NUMBER failed"

ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
pane="${TMUX_PANE:-none}"
run_id="${PI_DELEGATE_RUN_ID:-none}"
mkdir -p "$(dirname "$MERGE_LOG")"
printf '%s\t%s\t%s\t%s\t%s\n' "$ts" "$pane" "$run_id" "$PR_NUMBER" "$head_sha" >>"$MERGE_LOG"
echo "merge-pr: merged PR #$PR_NUMBER (head $head_sha), logged to $MERGE_LOG"
