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

RUN git clone https://github.com/example-user/dotfiles.git

RUN cd dotfiles && make install

SHELL ["/bin/zsh", "-c"]
