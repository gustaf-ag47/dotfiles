# Tmux session selector - attach to existing sessions or create new ones
# Shows: existing sessions, tmuxp configs, and option to create new
ftmuxp() {
	# Skip if already inside tmux
	if [[ -n $TMUX ]]; then
		return
	fi

	local choice
	local options=""
	local new_session="[+] Create New Session"

	# Get existing tmux sessions
	local sessions=""
	if tmux list-sessions &>/dev/null; then
		sessions=$(tmux list-sessions -F "[session] #{session_name} (#{session_windows} windows, #{?session_attached,attached,detached})" 2>/dev/null)
	fi

	# Get tmuxp configurations
	local configs=""
	if [[ -d "$XDG_CONFIG_HOME/tmuxp" ]]; then
		configs=$(ls "$XDG_CONFIG_HOME/tmuxp" 2>/dev/null | sed -e 's/\.yml$//' | sed 's/^/[config] /')
	fi

	# Build options list
	if [[ -n $sessions ]]; then
		options="$sessions"
	fi
	if [[ -n $configs ]]; then
		[[ -n $options ]] && options="$options\n$configs" || options="$configs"
	fi
	options="$new_session\n$options"

	# Show fzf selector
	choice=$(echo -e "$options" | fzf --height=40% --reverse --header="Select tmux session or config:")

	# Handle selection
	case "$choice" in
		"$new_session")
			tmux new-session
			;;
		\[session\]*)
			# Extract session name and attach
			local session_name=$(echo "$choice" | sed 's/\[session\] //' | cut -d' ' -f1)
			tmux attach-session -t "$session_name"
			;;
		\[config\]*)
			# Extract config name and load with tmuxp
			local config_name=$(echo "$choice" | sed 's/\[config\] //')
			tmuxp load "$XDG_CONFIG_HOME/tmuxp/$config_name"
			;;
		"")
			# User pressed Escape or Ctrl-C, don't start tmux
			return
			;;
	esac
}

fsb() {
	local pattern=$@
	local branches branch
	branches=$(git branch --all | awk 'tolower($0) ~ /'$pattern'/') &&
		branch=$(echo "$branches" |
			fzf-tmux --height 30% --reverse -1 -0 +m) &&
		if [ "$branch" = "" ]; then
			echo "[$0] No branch matches the provided pattern"
			return
		fi
	git checkout $(echo "$branch" | sed "s/.* //" | sed "s#remotes/[^/]*/##")
}

# Interactive git log browser with diff preview
fglog() {
	git log --oneline --color=always |
		fzf --ansi --no-sort --reverse --tiebreak=index \
			--preview 'git show --color=always {1}' \
			--preview-window=right:60%:wrap \
			--bind 'enter:execute(git show --color=always {1} | less -R)'
}

# Fuzzy git checkout - works with local and remote branches
fgco() {
	local branches branch
	branches=$(git branch -a --color=always | grep -v HEAD) &&
		branch=$(echo "$branches" |
			fzf --ansi --tac --preview-window=right:70% \
				--preview 'git log --oneline --color=always $(echo {} | sed "s/.* //" | sed "s#remotes/[^/]*/##") | head -20') &&
		git checkout $(echo "$branch" | sed "s/.* //" | sed "s#remotes/[^/]*/##")
}

# Interactive git branch delete
fgbd() {
	local branches branch
	branches=$(git branch --color=always | grep -v '\*') &&
		branch=$(echo "$branches" |
			fzf --ansi --multi \
				--preview 'git log --oneline --color=always {} | head -20') &&
		echo "$branch" | xargs -r git branch -d
}
