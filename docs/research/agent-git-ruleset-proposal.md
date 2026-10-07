# Server-side ruleset report: which repos agents push to

Companion to `docs/agent-git.md`. `agent-git`/`agent-gh` are the client-side
guard; GitHub rulesets are the server-side backstop for the same two risks
(force-push over someone's work, ref deletion), scoped per the brief: applied
only to `gustaf-ag47/*` repos, proposal-only everywhere else. The full
breakdown (company/project names, private repos) is not reproduced here
since this repo is public — see the private report referenced from the
`agent-git-guard` output file for that detail.

## Applied: `gustaf-ag47/*` (own account, public repos)

GitHub rulesets require GitHub Pro (or a public repo) on personal accounts.
Of the owner's repos, 3 are public and could take a ruleset today; the
private ones are blocked by the Pro gate (tracked privately, not listed
here); archived and branch-less repos were skipped.

Ruleset applied to each (`deletion` + `non_fast_forward` rules, target =
default branch, enforcement = active, no bypass actors — including the
owner):

| Repo | Default branch | Ruleset |
|---|---|---|
| dotfiles | master | id 24668843 |
| install-arch | master | id 24668844 |
| messenger | 4.4 | id 24668845 |

Verify / adjust: `gh api repos/gustaf-ag47/<repo>/rulesets`. Add a second
`ref_name.include` pattern (e.g. `refs/heads/release/*`) if/when a release
branch appears; none of these repos have one today.

## Proposal only: everything else

Private `gustaf-ag47` repos need GitHub Pro (or classic branch protection,
which doesn't have the ruleset gate) before the same rules can apply.
Org repos — both the shared day-job org and Gustaf's own smaller orgs — are
proposal-only per the brief's scope (`gustaf-ag47/*` only gets changes
applied from an agent run); the per-org breakdown and recommended next step
is in the private report.
