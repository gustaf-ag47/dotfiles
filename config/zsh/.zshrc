# autoload
fpath=($ZDOTDIR/external $fpath)
autoload -Uz compinit; compinit
autoload -Uz edit-command-line
autoload -Uz select-bracketed select-quoted
autoload -Uz surround

# external
autoload -Uz cursor_mode && cursor_mode
autoload -Uz custom_prompt && custom_prompt

setopt AUTO_PUSHD
setopt PUSHD_IGNORE_DUPS
setopt PUSHD_SILENT
setopt EXTENDED_GLOB        
setopt HIST_EXPIRE_DUPS_FIRST  
setopt HIST_FIND_NO_DUPS    
setopt HIST_IGNORE_DUPS     
setopt HIST_IGNORE_SPACE    
setopt HIST_VERIFY          
setopt INC_APPEND_HISTORY   
setopt SHARE_HISTORY        

# load modules
zmodload zsh/complist # For menuselect


if command -v pyenv > /dev/null; then
  eval "$(pyenv init -)"
fi

if [ $(command -v "fzf") ]; then
  source /usr/share/fzf/completion.zsh
  source /usr/share/fzf/key-bindings.zsh
fi

# Initialize zoxide (smart cd replacement)
if command -v zoxide > /dev/null; then
  eval "$(zoxide init zsh)"
fi

# Initialize starship prompt (if available)
if command -v starship > /dev/null; then
  eval "$(starship init zsh)"
fi

# Initialize Atuin (shell history sync)
if command -v atuin > /dev/null; then
  eval "$(atuin init zsh --disable-up-arrow)"
  # Use Ctrl+R for Atuin search (replaces fzf history)
  # Up arrow remains for standard history navigation
fi

_comp_options+=(globdots)
source $ZDOTDIR/external/completion.zsh
source $ZDOTDIR/external/bd.zsh

# Source zsh plugins with fallback locations
# Try local installation first, then system packages
if [ -f "$ZDOTDIR/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh" ]; then
    source "$ZDOTDIR/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh"
elif [ -f "/usr/share/zsh/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh" ]; then
    source "/usr/share/zsh/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh"
fi

if [ -f "$ZDOTDIR/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh" ]; then
    source "$ZDOTDIR/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh"
elif [ -f "/usr/share/zsh/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh" ]; then
    source "/usr/share/zsh/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh"
fi

source $ZDOTDIR/scripts/fzf.sh
source $ZDOTDIR/scripts/functions.zsh
source $ZDOTDIR/aliases

# Host-specific configuration (based on hostname)
HOST_ZSH_CONF="$DOTFILES/config/zsh/hosts/$(hostname).zsh"
[[ -f "$HOST_ZSH_CONF" ]] && source "$HOST_ZSH_CONF"

# zsh line editor
zle -N edit-command-line
zle -N paste-from-clipboard
zle -N select-quoted
zle -N select-bracketed
zle -N add-surround surround
zle -N change-surround surround
zle -N delete-surround surround

bindkey -v
bindkey '^?' backward-delete-char
bindkey -M menuselect 'h' vi-backward-char
bindkey -M menuselect 'k' vi-up-line-or-history
bindkey -M menuselect 'l' vi-forward-char
bindkey -M menuselect 'j' vi-down-line-or-history
bindkey -M vicmd v edit-command-line
bindkey -M vicmd cs change-surround
bindkey -M vicmd ds delete-surround
bindkey -M vicmd ys add-surround
bindkey -M visual S add-surround

bindkey -r '^l'
bindkey -r '^g'
bindkey -s '^g' 'clear\n'

for km in viopp visual; do
  bindkey -M $km -- '-' vi-up-line-or-history
  for c in {a,i}${(s..)^:-\'\"\`\|,./:;=+@}; do
    bindkey -M $km $c select-quoted
  done
  for c in {a,i}${(s..)^:-'()[]{}<>bB'}; do
    bindkey -M $km $c select-bracketed
  done
done

# Load local/private configurations (gitignored, personal use)
# Source personal environment variables
if [ -f "$DOTFILES/local/env/.env" ]; then
	source "$DOTFILES/local/env/.env"
fi

# Source personal zsh configurations
# Use nullglob to avoid errors when no .zsh files exist
if [ -d "$DOTFILES/local/config/zsh" ]; then
	setopt local_options nullglob
	for file in "$DOTFILES/local/config/zsh"/*.zsh; do
		[ -f "$file" ] && source "$file"
	done
fi

# Add local bin to PATH
if [ -d "$DOTFILES/local/bin" ]; then
	export PATH="$DOTFILES/local/bin:$PATH"
fi

if [ "$(tty)" = "/dev/tty1" ]; then
    choice=$(echo -e "Wayland\nXorg" | fzf)
    case $choice in
        Wayland) exec Hyprland ;;
        Xorg) startx ;;
    esac
fi

if [ "$(tty)" != "/dev/tty1" ]; then
  ftmuxp
fi
