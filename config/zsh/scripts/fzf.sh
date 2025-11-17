ftmuxp() {
	if [[ -n $TMUX ]]; then
		return
	fi

	# Check if there are saved tmux sessions to restore
	resurrect_dir="$XDG_DATA_HOME/tmux/resurrect"
	if [[ -d "$resurrect_dir" ]] && [[ -n "$(ls -A "$resurrect_dir")" ]]; then
		# Auto-restore last session with continuum
		if tmux list-sessions 2>/dev/null | grep -q .; then
			# Sessions exist, attach to the last one
			tmux attach-session
			return
		fi
	fi

	# Fallback to tmuxp if no saved sessions or tmuxp configs exist
	if [[ -d "$XDG_CONFIG_HOME/tmuxp" ]]; then
		ID="$(ls $XDG_CONFIG_HOME/tmuxp 2>/dev/null | sed -e 's/\.yml$//')"
		if [[ -n $ID ]]; then
			create_new_session="Create New Session"
			restore_session="Restore Last Session"
			
			options="${restore_session}\n${create_new_session}\n$ID"
			selection="$(echo $options | fzf | cut -d: -f1)"

			if [[ $selection == "${restore_session}" ]]; then
				# Try to restore or create new if no sessions to restore
				if ! tmux attach-session 2>/dev/null; then
					tmux new-session
				fi
			elif [[ $selection == "${create_new_session}" ]]; then
				tmux new-session
			elif [[ -n $selection ]]; then
				tmuxp load "$XDG_CONFIG_HOME/tmuxp/$selection"
			fi
			return
		fi
	fi

	# Simple fallback - try to attach or create new
	if ! tmux attach-session 2>/dev/null; then
		tmux new-session
	fi
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
