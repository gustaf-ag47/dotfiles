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
	if grep -qiE 'do not merge|no-merge|don.?t merge' "$BRIEF"; then
		echo "merge-pr: refused: brief $BRIEF says not to merge PR #$PR_NUMBER" >&2
		exit 2
	fi
fi

agent_login="$(gh api user -q .login)" || die "could not resolve agent identity (gh api user)"
[ -n "$agent_login" ] || die "empty agent identity from gh api user"

repo_args=()
for ((i = 0; i < ${#GH_ARGS[@]}; i++)); do
	if [ "${GH_ARGS[i]}" = "--repo" ] && [ $((i + 1)) -lt "${#GH_ARGS[@]}" ]; then
		repo_args=(--repo "${GH_ARGS[i + 1]}")
		break
	fi
done

pr_json="$(gh pr view "$PR_NUMBER" "${repo_args[@]}" --json author,commits,headRefOid,state 2>&1)" ||
	die "gh pr view $PR_NUMBER failed: $pr_json"

pr_state="$(printf '%s' "$pr_json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["state"])')"
if [ "$pr_state" = "MERGED" ]; then
	echo "merge-pr: refused: PR #$PR_NUMBER is already merged; not logging another merge" >&2
	exit 5
fi

pr_author="$(printf '%s' "$pr_json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["author"]["login"])')"
head_sha="$(printf '%s' "$pr_json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["headRefOid"])')"
other_logins="$(printf '%s' "$pr_json" | python3 -c '
import json, sys
d = json.load(sys.stdin)
logins = set()
for c in d.get("commits", []):
    for role in ("authors",):
        for a in c.get(role) or []:
            login = a.get("login")
            if login:
                logins.add(login)
print("\n".join(sorted(logins)))
')"

if [ "$pr_author" != "$agent_login" ]; then
	echo "merge-pr: refused: PR #$PR_NUMBER was opened by '$pr_author', not the agent identity '$agent_login'" >&2
	exit 3
fi

bad_commit_logins=""
while IFS= read -r login; do
	[ -z "$login" ] && continue
	if [ "$login" != "$agent_login" ]; then
		bad_commit_logins="${bad_commit_logins}${bad_commit_logins:+,}${login}"
	fi
done <<<"$other_logins"

if [ -n "$bad_commit_logins" ]; then
	echo "merge-pr: refused: PR #$PR_NUMBER has commits authored by non-agent login(s): $bad_commit_logins" >&2
	exit 3
fi

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
