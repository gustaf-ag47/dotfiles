# User preferences (global, appended to every Pi session)

## Where documents go

- Documentation, notes, research write-ups, plans, incident reports, and
  decision records belong in the notes vault at `$NOTES`
  (`~/sync/Vault`), not in source repositories.
- Source repositories under `$SYNC/src` stay code: implementation, tests,
  configuration, and the minimal README/inline docs needed to build and run.
- When work in a repo produces a document (research, analysis, plan,
  post-mortem), write it to an appropriate place in `$NOTES` and, if useful,
  reference it from the repo by path - do not commit the document itself.
- Exception: a repo's own operational contract may require in-repo docs
  (e.g. structured inventory validated by repo tooling). Keep those minimal
  and put the narrative/decision context in `$NOTES`.
