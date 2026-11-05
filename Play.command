#!/bin/zsh
# Double-click to play: reimports new models (otherwise Godot uses the old ones) and opens the game.
cd "$(dirname "$0")"
GODOT=/Applications/Godot.app/Contents/MacOS/Godot
"$GODOT" --headless --import --path . > /dev/null 2>&1
"$GODOT" --path . > /dev/null 2>&1 &
disown
osascript -e 'tell application "Terminal" to close (every window whose name contains "Play.command")' > /dev/null 2>&1 &
exit 0
