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

	# Check if docker is available
	if ! command -v docker &>/dev/null; then
		echo "Error: Docker is not installed or not in PATH"
		return 1
	fi

	# Check if docker daemon is running
	if ! docker info &>/dev/null; then
		echo "Error: Docker daemon is not running"
		return 1
	fi

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

# Company-specific functions have been moved to local/config/zsh/work.zsh
# This keeps work-related code separate from public dotfiles

paste-from-clipboard() {
	if [ -n "${WAYLAND_DISPLAY:-}" ]; then
		LBUFFER+=$(wl-paste)
	elif [ -n "${DISPLAY:-}" ]; then
		LBUFFER+=$(xclip -o -selection clipboard)
	else
		echo "No display server detected"
	fi
}

vman() {
	nvim -c "SuperMan $*"

	if [ "$?" != "0" ]; then
		echo "No manual entry for $*"
	fi
}

uuid() {
	local generated_uuid=$(uuidgen)
	if [ -n "${WAYLAND_DISPLAY:-}" ]; then
		echo "$generated_uuid" | wl-copy
	elif [ -n "${DISPLAY:-}" ]; then
		echo "$generated_uuid" | xclip -selection clipboard
	else
		echo "$generated_uuid"
		return
	fi
	echo "UUID copied to clipboard: $generated_uuid"
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
