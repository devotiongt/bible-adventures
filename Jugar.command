#!/bin/zsh
# Doble clic para jugar: reimporta los modelos nuevos (si no, Godot usa los viejos) y abre el juego.
cd "$(dirname "$0")"
GODOT=/Applications/Godot.app/Contents/MacOS/Godot
"$GODOT" --headless --import --path . > /dev/null 2>&1
"$GODOT" --path . > /dev/null 2>&1 &
disown
osascript -e 'tell application "Terminal" to close (every window whose name contains "Jugar.command")' > /dev/null 2>&1 &
exit 0
