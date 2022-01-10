ftmuxp() {
	if [[ -n $TMUX ]]; then
		return
	fi

	ID="$(ls $XDG_CONFIG_HOME/tmuxp | sed -e 's/\.yml$//')"
	if [[ -z $ID ]]; then
		tmux new-session
	fi

	create_new_session="Create New Session"

	ID="${create_new_session}\n$ID"
	ID="$(echo $ID | fzf | cut -d: -f1)"

	if [[ $ID == "${create_new_session}" ]]; then
		tmux new-session
	elif [[ -n $ID ]]; then
		tmuxp load "$XDG_CONFIG_HOME/tmuxp/$ID"
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
