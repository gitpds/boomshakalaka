#!/bin/bash
# ttyd wrapper script with Midnight Command theme

THEME='theme={"background":"#060a14","foreground":"#ffffff","cursor":"#ff8c00","cursorAccent":"#060a14","selectionBackground":"rgba(255,140,0,0.3)"}'

exec /usr/local/bin/ttyd -p 7681 -W -t "$THEME" tmux new-session -A -s dashboard
