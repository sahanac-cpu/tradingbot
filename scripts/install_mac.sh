#!/bin/bash
# Installs the bot as a background service on macOS (launchd).
# - starts automatically when you log in, restarts itself if it crashes
# - keeps the Mac awake while it runs (caffeinate)
# - no VS Code or terminal needs to stay open
# Usage:  bash scripts/install_mac.sh            (asks for your Alpaca PAPER keys once)
set -e
SRC="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$HOME/tradingbot-service"
ENVF="$HOME/.tradingbot.env"
PLIST="$HOME/Library/LaunchAgents/com.tradingbot.plist"
PY="$(command -v python3)"

echo "== Trading bot background installer =="
# macOS blocks background services from reading Downloads/Desktop/Documents,
# so the service runs from its own copy in your home folder.
mkdir -p "$DEST"
# keep the service's own memory: never overwrite its model, account, trades or logs
rsync -a --exclude logs --exclude model.json --exclude account.json --exclude trades.csv \
  --exclude data --exclude "backtest_*" --exclude history --exclude "model_*.json" --exclude "arena_*.csv" --exclude today.json --exclude sim_trades.csv "$SRC/" "$DEST/"
echo "bot copied to $DEST"

if [ ! -f "$ENVF" ] || [ "$1" = "--new-keys" ]; then
  read -r -p "Alpaca PAPER API key ID: " KEY
  read -r -s -p "Alpaca PAPER secret key (hidden): " SECRET; echo
  printf 'APCA_API_KEY_ID=%s\nAPCA_API_SECRET_KEY=%s\n' "$KEY" "$SECRET" > "$ENVF"
  chmod 600 "$ENVF"
  echo "keys saved to $ENVF (only your user can read it)"
fi

SYMBOLS="${SYMBOLS:-}"
cat > "$DEST/scripts/start.sh" <<EOS
#!/bin/bash
cd "$DEST"
set -a; . "$ENVF"; set +a
exec /usr/bin/caffeinate -i "$PY" -u -m bot.run --broker alpaca --no-browser $SYMBOLS
EOS
chmod +x "$DEST/scripts/start.sh"
mkdir -p "$DEST/logs" "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<EOS
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.tradingbot</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$DEST/scripts/start.sh</string></array>
  <key>WorkingDirectory</key><string>$DEST</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>StandardOutPath</key><string>$DEST/logs/bot.log</string>
  <key>StandardErrorPath</key><string>$DEST/logs/bot.log</string>
</dict></plist>
EOS

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
sleep 5
echo
tail -5 "$DEST/logs/bot.log" 2>/dev/null || true
echo
echo "Installed and running. Dashboard: http://localhost:8000"
echo "Check it any time:  bash ~/tradingbot-service/scripts/status.sh"
