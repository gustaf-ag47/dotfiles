# Claude Code auth for local shells.
#
# Keep the secret value in $HOME/cctoken (or the existing cache file), never in
# this helper. Startup files source this helper so zsh, bash, and tmux-launched
# shells inherit the same Claude Code OAuth token.

_cc_source_if_private() {
	_cc_file="$1"
	[ -r "$_cc_file" ] || return 1
	_cc_mode="$(stat -c '%a' "$_cc_file" 2>/dev/null || printf '')"
	case "$_cc_mode" in
		*00) ;;
		*) return 1 ;;
	esac
	# shellcheck disable=SC1090
	. "$_cc_file"
}

_cc_token_file="${HOME:-}/cctoken"
_cc_token_cache="${XDG_CACHE_HOME:-${HOME:-}/.cache}/claude-code-token.env"

# Quota-aware selection: claude-token-refresh probes every token in $cctoken
# and exports the one with the most weekly headroom (rolling over automatically
# when the active token nears its cap). It caches the pick for 5 min, so this is
# a cheap file read on most shells and one Haiku-token probe at most every 5 min.
_cc_apply_refresh() {
	command -v claude-token-refresh >/dev/null 2>&1 || return 1
	_cc_out="$(claude-token-refresh --quiet 2>/dev/null)" || return 1
	[ -n "$_cc_out" ] || return 1
	eval "$_cc_out"
	unset _cc_out
	return 0
}

if [ -n "${HOME:-}" ]; then
	# 1) Quota-aware refresh (preferred). 2) Last good cached pick (offline).
	# 3) Raw cctoken as a last resort (note: last export line wins, no quota check).
	if _cc_apply_refresh; then
		: "${CLAUDE_CODE_TOKEN_SOURCE:=$_cc_token_file}"
		export CLAUDE_CODE_TOKEN_SOURCE
	elif _cc_source_if_private "$_cc_token_cache"; then
		: "${CLAUDE_CODE_TOKEN_SOURCE:=$_cc_token_cache}"
		export CLAUDE_CODE_TOKEN_SOURCE
	elif _cc_source_if_private "$_cc_token_file"; then
		export CLAUDE_CODE_TOKEN_SOURCE="$_cc_token_file"
	fi
fi

case "${CLAUDE_CODE_OAUTH_TOKEN:-}" in
	sk-ant-oat*) export CLAUDE_CODE_OAUTH_TOKEN ;;
	*) unset CLAUDE_CODE_OAUTH_TOKEN ;;
esac

# Route every session through the local hot-swap proxy when it is running, so a
# long-lived `claude` rotates to a fresh token mid-session (the env-var token
# above is read once at launch and cannot rotate on its own). RESILIENT: only
# set the base URL when the proxy service is actually active — otherwise leave it
# unset so sessions fall back to the read-once token rather than failing to reach
# the API. The token stays exported either way (claude needs a launch credential;
# the proxy overrides the Authorization header per request).
_cc_proxy_port="${CC_PROXY_PORT:-8788}"
_cc_proxy_url="http://127.0.0.1:${_cc_proxy_port}"
if [ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ] && command -v systemctl >/dev/null 2>&1 \
	&& systemctl --user is-active --quiet claude-token-proxy 2>/dev/null; then
	export ANTHROPIC_BASE_URL="$_cc_proxy_url"
elif [ "${ANTHROPIC_BASE_URL:-}" = "$_cc_proxy_url" ]; then
	# Proxy not active but a base URL inherited from a prior shell still points at
	# it — clear ONLY our own URL (leave any custom gateway alone) so we fall back
	# to the read-once token instead of dialing a dead local port.
	unset ANTHROPIC_BASE_URL
fi

unset -f _cc_source_if_private _cc_apply_refresh 2>/dev/null || true
unset _cc_file _cc_mode _cc_token_file _cc_token_cache _cc_out _cc_proxy_port _cc_proxy_url
