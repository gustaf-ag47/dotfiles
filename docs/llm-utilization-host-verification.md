# LLM utilization host verification

`python3 scripts/llm_host_smoke.py` runs the required read-only checks and emits only a
versioned JSON checklist. Command output is discarded; it never records provider
responses, credentials, cookies, account IDs, or report contents. `--list` prints the
contract without running checks.

Run it separately from each checkout. The cache path and mode in the result are
metadata only; do not compare or copy cache contents between hosts. Capture the
result in a host-local scratch file if a longer-lived record is needed.

## Recovery

- **Expired OAuth:** use the provider/Pi's normal interactive login manually, then
  rerun the smoke suite. The report and smoke script never refresh credentials.
- **Unavailable news:** retain the stale/unavailable indication and retry later;
  do not substitute unofficial sources or alter routing.
- **Proxy outage:** treat `_usage` and `_route` checks as failed, recover the local
  user service using the existing operator procedure, and do not change routes or
  enable spending fallbacks.
- **Changed provider surface:** leave the affected adapter as unknown/unavailable
  until a redacted fixture and test are updated.

Each host must have its own installation, credentials, cache, proxy state, and
report timestamps. This procedure does not use `scp`, shared cache directories, or
copied authentication/browser state.
