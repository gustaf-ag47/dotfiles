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

## Ordered follow-up

After source/resource convergence, diagnose laptop Fable `??` usage for the account
identified by the user. Distinguish missing/expired response-header observations,
OAuth usage scope denial, bucket mapping and rendering. Unknown is not zero or
unlimited. That investigation should start read-only and retain credential privacy.
