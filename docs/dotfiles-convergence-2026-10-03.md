# Laptop / skrubben convergence — 2026-10-03

Scope: Dotfiles/Pi work from the laptop session and skrubben's Dotfiles panes.
Unrelated product repositories, private operator notes and active deployments are not part
of this convergence and must not be stopped or committed incidentally.

## Preserved and completed

- Original tracked changes were backed up on each host under
  `~/.local/state/dotfiles-converge/2026-10-03/` before editing or restoring any path.
  These host-local patches are recovery artifacts, not repository content.
- **Neovim:** kept the useful lock updates; corrected incompatible Treesitter main
  back to legacy master for go.nvim, restored Telescope's 0.1.x branch, aligned
  Refactoring's 1.0 branch, and enforced those branches in Lazy specs. See
  [validation and limits](nvim-lock-convergence.md). Tests used isolated plugin/config
  copies, not the user's running editor or its plugin checkout.
- **Delegation:** integrated skrubben's coordination/80%-context/result-line changes
  and updated the watcher to recognize the new contract plus legacy handshakes.
  Added wrapped/long-output, numeric-session and originating-pane regressions.
  See [the actual contract](pi-delegate-contract.md). Mailbox ACK bookkeeping remains
  distinct from noisy child ACK messages.
- **Mail handlers:** Thunderbird had generated machine-specific desktop IDs, some
  already missing on the laptop. Both machines have the distribution-provided
  `org.mozilla.Thunderbird.desktop`; mailto, message/rfc822, mid and net.thunderbird
  now reference that stable ID. Other application associations are unchanged.
- **Browser verification:** read-only inspection and a bounded synthetic Jev/Pi
  typing/clicking loop passed from both hosts through the existing Neko CDP browser.
  No normal desktop Chrome profile was changed. See [browser evidence](jev-ultrafast.md).
  The fixture test creates and closes only its own blank tab and named daemon.

## Deployment expectations

Both master checkouts must reach the same published commit via ordinary fast-forward
updates; remote pending edits are restored only after checking them against the
private backup and confirming the reviewed commits preserve their intent. Run
`bin/pi-setup --apply` on each host; credentials/settings/sessions are not overwritten.

Host-local runtime state is intentionally not made byte-identical: OAuth stores,
Jev keys, typing preferences, browser profiles, caches and test backups stay private
and out of git. Both hosts already passed Grok OAuth/Jev/Pi-typing checks. Shared
Grok refresh credentials remain an explicitly accepted convenience trade-off, not
new independent account quota.

Neovim's installed plugin data may differ until `:Lazy restore` is performed in a
safe editor-maintenance window. The source lock/specs are authoritative; this
closeout does not silently replace plugin trees underneath active editors.

Skrubben's proxy process was older than its checkout. It was restarted after two
idle-connection checks to load the current Grok observer and header timestamps.
The old process had no persistence file at the expected location, so the attempted
pre-restart file backup was absent and the header cache initially became unknown.
Normal subsequent Fable traffic repopulated a timestamped reading; the new process
persists it, and a private post-upgrade state backup was taken. Future migrations
from old versions should capture the live `/_usage` view as well as any on-disk
state before restart. No missing observations were invented or copied across hosts.

## Follow-up completed

After source/resource convergence, the laptop Fable `??` reading was traced to a
scope-denied quota endpoint plus a missing current Fable-specific header, not a
percentage calculation failure. The reporter now keeps the unknown bucket visible,
explains why, avoids a fabricated full allowance after resets, and distinguishes a
real zero-usage observation from missing data. See [quota-reading semantics](llm-usage-unknown.md).
No Anthropic credentials, account settings, inference probes or routing policy were changed.

## Additional work that arrived during closeout

A Google Code Assist integration was created in another pane during closeout.
The initial text-only/CLI-fallback prototype was held and preserved on
`feat/google-code-assist-proxy`. Its owner subsequently fixed project/model selection,
removed the second-agent fallback, and implemented a native Gemini API shim with
real Pi tool calling and quota reporting. That revised implementation is now on
`master`; the laptop service is active and verified. The earlier hold no longer
applies to this native path. See [current status](google-code-assist-proxy.md).

The PC did not have an Antigravity client or OAuth session at review time. Source
and resources can be synchronized independently, but Google credential provisioning
must be explicit; no Google credential is silently copied as part of a git update.
No new subscription or default-provider change was made.

During runtime checks, the copied Grok access token on the PC had expired while the
laptop's CLI had refreshed its own. Running the official `grok models` command on the
PC refreshed successfully without a new login or an inference request. This is the
recommended first recovery step for an expired CLI-backed token; interactive login
is the fallback if refresh fails. Credentials are still host-local runtime data.
