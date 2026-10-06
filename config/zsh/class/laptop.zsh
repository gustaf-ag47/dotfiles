# Laptop-class zsh overlay (sourced by .zshrc via dotfiles-profile.env).

alias brightness='brightnessctl'

# First system battery by type, not by name (BAT0 on the XPS 15, but vendors
# differ). scope=Device excludes peripherals such as a wireless mouse.
_system_battery() {
  local d
  for d in /sys/class/power_supply/*(N); do
    [[ "$(<$d/type)" == Battery ]] || continue
    [[ -r $d/scope && "$(<$d/scope)" == Device ]] && continue
    print -r -- $d
    return 0
  done
  return 1
}
# These were aliases; drop them so a re-sourced shell gets the functions.
unalias battery charging 2>/dev/null
function battery { local b; b=$(_system_battery) && print -r -- "$(<$b/capacity)"; }
function charging { local b; b=$(_system_battery) && print -r -- "$(<$b/status)"; }
