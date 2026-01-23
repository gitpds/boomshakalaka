#!/bin/bash
# ttyd wrapper for bottom terminal pane

THEME='theme={"background":"#122637","foreground":"#fefff1","cursor":"#f0cb09","cursorAccent":"#fefff1","selectionBackground":"rgba(240,203,9,0.3)"}'

exec /usr/local/bin/ttyd -p 7682 -W -t "$THEME" tmux new-session -A -s dashboard-bottom
