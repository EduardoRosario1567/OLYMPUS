#!/bin/zsh
set -e

ROOT="${1:-$HOME/Projects/OLYMPUS}"
APP="$HOME/Desktop/OLYMPUS.app"
LAUNCHER="$APP/Contents/MacOS/launcher"

mkdir -p "$APP/Contents/MacOS"
cat > "$LAUNCHER" <<EOF
#!/bin/zsh
ROOT="$ROOT"
osascript <<'APPLESCRIPT'
tell application "Terminal"
    activate
    do script "cd '$ROOT' && ./scripts/olympus_dev.sh"
end tell
APPLESCRIPT
EOF
chmod +x "$LAUNCHER"
echo "OLYMPUS.app -> $ROOT"
