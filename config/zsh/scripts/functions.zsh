function up() {
	cd "$(printf "%0.s../" $(seq 1 $1))"
}

function mkcd() {
	mkdir -p "$1" && cd "$1"
}

extract() {
	if [ -f $1 ]; then
		case $1 in
		*.tar.bz2) tar xjf $1 ;;
		*.tar.gz) tar xzf $1 ;;
		*.bz2) bunzip2 $1 ;;
		*.rar) rar x $1 ;;
		*.gz) gunzip $1 ;;
		*.tar) tar xf $1 ;;
		*.tbz2) tar xjf $1 ;;
		*.tgz) tar xzf $1 ;;
		*.zip) unzip $1 ;;
		*.Z) uncompress $1 ;;
		*.7z) 7z x $1 ;;
		*) echo "'$1' cannot be extracted via extract()" ;;
		esac
	else
		echo "'$1' is not a valid file"
	fi
}

docker-nuke() {
	local project=$1

	if [ -z "$project" ]; then
		echo "Please provide a project name."
		return 1
	fi

	docker stop $(docker ps -qa --filter "name=${project}") 2>/dev/null
	docker rm $(docker ps -qa --filter "name=${project}") 2>/dev/null

	docker rmi -f $(docker images -q --filter "label=project=$project") 2>/dev/null
	docker rmi -f $(docker images -q --filter "reference=${project}*") 2>/dev/null

	docker volume rm $(docker volume ls -q --filter "name=${project}") 2>/dev/null

	docker network rm $(docker network ls -q --filter "name=${project}") 2>/dev/null

	echo "Docker resources for project '$project' have been cleaned up."
}

ss-code-nuke() {
	docker-nuke
	sudo rm -rf docker/mysql/data
	sudo rm -rf var
	sudo rm -rf vendor
	make build
	make uph && make composer && make refresh-db
}

ss-update() {
	base_dir=$HOME/src
	folders=("frontend-repo" "work-company-api" "work-company-api-platform")

	for folder in "${folders[@]}"; do
		cd "$base_dir/$folder" || continue
		echo "Updating '$folder'"

		current_branch=$(git symbolic-ref --short HEAD)

		saved_branch="$current_branch"

		git checkout master
		git pull --rebase

		git checkout develop
		git pull --rebase

		git checkout "$saved_branch"

		echo "Switched back to branch '$saved_branch' in '$folder'"
	done
}

paste-from-clipboard() {
	LBUFFER+=$(xclip -o -selection clipboard)
}

vman() {
	nvim -c "SuperMan $*"

	if [ "$?" != "0" ]; then
		echo "No manual entry for $*"
	fi
}

uuid() {
	uuidgen | wl-copy
}

g() {
	git commit --amend -a --no-edit && git push -f
}

r() {
	current_branch=$(git symbolic-ref --short HEAD)

	if [[ $current_branch == *"hotfix/"* ]] || [[ $current_branch == *"feature/"* ]] || [[ $current_branch == *"chore/"* ]]; then
		target_branch="master"
	else
		echo "Error: Unsupported branch type. Branch name must include 'feature/', 'chore/', or 'hotfix/'"
	fi

	echo "Rebasing $current_branch to $target_branch..."
	git fetch
	git checkout $target_branch
	git pull origin $target_branch --rebase
	git checkout $current_branch
	git rebase $target_branch
	echo "Rebase complete."
}

# Tmux session management functions
tmux-save() {
	if [[ -n $TMUX ]]; then
		echo "Saving tmux session..."
		tmux run-shell "$XDG_DATA_HOME/tmux/plugins/tmux-resurrect/scripts/save.sh"
		echo "Session saved!"
	else
		echo "Not in a tmux session"
	fi
}

tmux-restore() {
	if [[ -n $TMUX ]]; then
		echo "Restoring tmux session..."
		tmux run-shell "$XDG_DATA_HOME/tmux/plugins/tmux-resurrect/scripts/restore.sh"
		echo "Session restored!"
	else
		echo "Not in a tmux session. Starting new session with restore..."
		tmux new-session -d
		tmux run-shell "$XDG_DATA_HOME/tmux/plugins/tmux-resurrect/scripts/restore.sh"
		tmux attach-session
	fi
}

tmux-clean-old-sessions() {
	echo "Cleaning up old tmux sessions..."
	resurrect_dir="$XDG_DATA_HOME/tmux/resurrect"
	if [[ -d "$resurrect_dir" ]]; then
		# Keep only the last 5 session files
		ls -t "$resurrect_dir"/tmux_resurrect_*.txt 2>/dev/null | tail -n +6 | xargs rm -f
		echo "Old session files cleaned up"
	fi
}
