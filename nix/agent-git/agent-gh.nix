# `agent-gh`: wraps the real `gh` and refuses the destructive calls Pi agents
# must not make unsupervised. Everything else passes straight through.
#
# Refused unconditionally:
#   - `gh repo delete`
#   - `gh api ... -X DELETE` against a repo-deletion, ref-deletion or
#     branch-deletion endpoint (`DELETE /repos/{o}/{r}`,
#     `DELETE /repos/{o}/{r}/git/refs/...`, `DELETE
#     /repos/{o}/{r}/branches/{b}` family)
#
# Refused unless the PR's author is the authenticated (agent) account:
#   - `gh pr close`
#   - `gh api .../pulls/{n} -X PATCH` with `state` set to `closed` in the body
#
# Rationale and allow-rule for branch deletion: see docs/agent-git.md. Agents
# may only let their own branches disappear via GitHub's auto-delete-on-merge
# setting, never by calling the delete API/CLI themselves.
{ writeShellApplication, gh, jq }:

writeShellApplication {
  name = "gh";
  runtimeInputs = [ gh jq ];
  text = ''
    real_gh() { command gh "$@"; }

    blocked() {
      echo "blocked for agents: ask Gustaf (via Hermes) — $1" >&2
      exit 1
    }

    # Best-effort: the account agents push as. Never fatal if offline/unauth.
    current_login() {
      real_gh api user --jq .login 2>/dev/null || echo ""
    }

    pr_author() {
      # $1=owner/repo (or empty for gh's own resolution), $2=pr number
      if [ -n "''${1:-}" ]; then
        real_gh api "repos/$1/pulls/$2" --jq .user.login 2>/dev/null || echo ""
      else
        real_gh pr view "$2" --json author --jq .author.login 2>/dev/null || echo ""
      fi
    }

    # --- gh repo delete ---------------------------------------------------
    if [ "''${1:-}" = "repo" ] && [ "''${2:-}" = "delete" ]; then
      blocked "gh repo delete is disabled for agents"
    fi

    # --- gh pr close / gh pr merge --delete-branch on someone else's PR ---
    if [ "''${1:-}" = "pr" ] && [ "''${2:-}" = "close" ]; then
      pr_arg="''${3:-}"
      me="$(current_login)"
      author="$(pr_author "" "$pr_arg")"
      if [ -z "$me" ] || [ -z "$author" ] || [ "$me" != "$author" ]; then
        blocked "gh pr close on a PR not authored by the agent account is disabled"
      fi
    fi

    # --- gh api: inspect verb/path/body for DELETE and close-via-PATCH ---
    if [ "''${1:-}" = "api" ]; then
      shift
      path=""
      method="GET"
      body_state=""
      args=("$@")
      i=0
      n=''${#args[@]}
      while [ "$i" -lt "$n" ]; do
        arg="''${args[$i]}"
        case "$arg" in
          -X|--method)
            i=$((i+1)); method="''${args[$i]:-GET}" ;;
          -X*) method="''${arg#-X}" ;;
          -f|--raw-field|-F|--field)
            i=$((i+1))
            field="''${args[$i]:-}"
            case "$field" in
              state=closed) body_state="closed" ;;
            esac ;;
          -*) : ;;
          *) [ -z "$path" ] && path="$arg" ;;
        esac
        i=$((i+1))
      done
      method_upper=$(printf '%s' "$method" | tr '[:lower:]' '[:upper:]')

      if [ "$method_upper" = "DELETE" ]; then
        case "$path" in
          repos/*/*/git/refs/*) blocked "gh api DELETE on a git ref is disabled" ;;
          repos/*/*/branches/*) blocked "gh api DELETE on a branch is disabled" ;;
          repos/*/*) blocked "gh api DELETE on a repo is disabled" ;;
        esac
      fi

      if [ "$method_upper" = "PATCH" ] && [ "$body_state" = "closed" ]; then
        case "$path" in
          repos/*/*/pulls/*)
            owner_repo=$(printf '%s' "$path" | cut -d/ -f2-3)
            pr_num=$(printf '%s' "$path" | sed -E 's#.*/pulls/([0-9]+).*#\1#')
            me="$(current_login)"
            author="$(pr_author "$owner_repo" "$pr_num")"
            if [ -z "$me" ] || [ -z "$author" ] || [ "$me" != "$author" ]; then
              blocked "gh api PATCH state=closed on a PR not authored by the agent account is disabled"
            fi
            ;;
        esac
      fi

      real_gh api "''${args[@]}"
      exit $?
    fi

    real_gh "$@"
    exit $?
  '';
}
