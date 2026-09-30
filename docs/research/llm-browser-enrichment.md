# Read-only browser enrichment

`llm_browser.py` is an opt-in parser for data supplied by an operator-approved
existing CDP session. A caller may pass rendered page fields and page network
responses to `inspect_snapshot`; normal `llm-usage` does not require a browser.

Only normalized reset expiry/count and offer presence are retained. URLs are
reduced to a provider usage-page category, and cookies, bearer tokens, raw
responses, and account identifiers are never returned or cached. Cache files
are host-local and written mode `0600` in a mode `0700` directory.

`assert_read_only` permits GET usage-page reads only. It rejects non-GET
requests and mutation-shaped checkout, billing, reset, reload, purchase, and
plan URLs. The adapter cannot purchase, apply resets, reload, change plans, or
modify settings. Login expiry, blocked responses, malformed pages, and missing
fields remain explicit unavailable/unknown states.

Automated tests use synthetic page and network fixtures only; no authenticated
browser session or credential is used.
