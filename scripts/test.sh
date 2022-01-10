#!/bin/bash

docker build -t dotfiles-test . --no-cache
docker run -it dotfiles-test /bin/zsh
