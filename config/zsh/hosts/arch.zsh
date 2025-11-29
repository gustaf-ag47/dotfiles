# Host-specific zsh config for: arch (Dell XPS 15 laptop)
# This file is sourced by .zshrc based on hostname

# Laptop-specific aliases
alias brightness='brightnessctl'

# Power management aliases
alias bat='cat /sys/class/power_supply/BAT0/capacity'
alias charging='cat /sys/class/power_supply/BAT0/status'

# Laptop-specific environment variables (if any)
# export SOME_LAPTOP_VAR="value"
