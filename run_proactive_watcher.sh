#!/bin/zsh
source "$HOME/.zshrc"
cd "$HOME/Akira"
exec "$HOME/Akira/.venv/bin/python" "$HOME/Akira/proactive_watcher.py"
