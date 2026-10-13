#!/bin/bash
# Offline supervisor regression: all commands including suspend are fakes.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
CACHE=${XDG_CACHE_HOME:-$HOME/.cache}
mkdir -p "$CACHE"
SCRATCH=$(mktemp -d "$CACHE/hyprlock-safe-test.XXXXXXXX")
trap 'rm -rf "$SCRATCH"' EXIT
mkdir -p "$SCRATCH/bin"
printf 'tty3\n' > "$SCRATCH/active"
export HYPRLOCK_ACTIVE_VT_FILE="$SCRATCH/active" XDG_SESSION_ID=1 TEST_DIR="$SCRATCH"
export PATH="$SCRATCH/bin:$PATH"

for name in hyprlock logger hyprctl loginctl sleep systemctl notify-send; do
    : > "$SCRATCH/bin/$name"
    chmod +x "$SCRATCH/bin/$name"
done

# Fake hyprlock returns 42 N times, then 0. No real session ever locks.
tee "$SCRATCH/bin/hyprlock" >/dev/null <<'EOF'
#!/bin/bash
n=$(< "$TEST_DIR/count")
echo $((n+1)) > "$TEST_DIR/count"
if (( n < $(< "$TEST_DIR/failures") )); then exit 42; fi
EOF
tee "$SCRATCH/bin/logger" >/dev/null <<'EOF'
#!/bin/bash
printf '%s\n' "$*" >> "$TEST_DIR/journal"
EOF
tee "$SCRATCH/bin/hyprctl" >/dev/null <<'EOF'
#!/bin/bash
printf '%s\n' "$*" >> "$TEST_DIR/hyprctl"
EOF
tee "$SCRATCH/bin/loginctl" >/dev/null <<'EOF'
#!/bin/bash
case "$*" in
    *'-p VTNr'*) echo 3 ;;
    *'-p Type'*) echo wayland ;;
    *) exit 1 ;;
esac
EOF
tee "$SCRATCH/bin/sleep" >/dev/null <<'EOF'
#!/bin/bash
# No waiting in fake crash loop.
exit 0
EOF
tee "$SCRATCH/bin/systemctl" >/dev/null <<'EOF'
#!/bin/bash
printf '%s\n' "$*" >> "$TEST_DIR/suspend"
EOF
tee "$SCRATCH/bin/notify-send" >/dev/null <<'EOF'
#!/bin/bash
exit 0
EOF

printf '2\n' > "$SCRATCH/failures"
printf '0\n' > "$SCRATCH/count"
bash "$ROOT/bin/hyprlock-safe"
[[ $(< "$SCRATCH/count") == 3 ]]
[[ $(wc -l < "$SCRATCH/journal") == 2 ]]
grep -q 'status=42' "$SCRATCH/journal"
[[ $(wc -l < "$SCRATCH/hyprctl") == 2 ]]
grep -q 'keyword misc:allow_session_lock_restore 1' "$SCRATCH/hyprctl"
[[ ! -e $SCRATCH/suspend ]]

# A crash while on another VT must not start a replacement until returning.
printf '1\n' > "$SCRATCH/failures"
printf '0\n' > "$SCRATCH/count"
printf 'tty2\n' > "$SCRATCH/active"
bash "$ROOT/bin/hyprlock-safe" &
waiter=$!
/usr/bin/sleep 0.2
[[ $(< "$SCRATCH/count") == 1 ]]
printf 'tty3\n' > "$SCRATCH/active"
wait "$waiter"
[[ $(< "$SCRATCH/count") == 2 ]]

printf '10\n' > "$SCRATCH/failures"
printf '0\n' > "$SCRATCH/count"
: > "$SCRATCH/journal"
bash "$ROOT/bin/hyprlock-safe"
[[ $(< "$SCRATCH/count") == 5 ]]
grep -q 'crashed 5 times rapidly' "$SCRATCH/journal"
grep -q '^suspend$' "$SCRATCH/suspend"
echo 'hyprlock-safe: crash recovery and rapid-crash suspend OK'