FROM archlinux:latest

RUN pacman -Syu --noconfirm \
	base-devel \
	curl \
	firefox \
	fzf \
	git \
	neovim \
	rsync \
	sudo \
	tmux \
	zsh && \
	pacman -Scc --noconfirm

RUN useradd -m -G wheel tester && echo 'tester ALL=(ALL) NOPASSWD: ALL' >/etc/sudoers.d/tester

USER tester
WORKDIR /home/tester

# Clone dotfiles - replace with your own repo URL
ARG DOTFILES_REPO=https://github.com/example/dotfiles.git
RUN git clone ${DOTFILES_REPO}

RUN cd dotfiles && make install

SHELL ["/bin/zsh", "-c"]
