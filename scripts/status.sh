#!/bin/bash
# Is the background bot running? Shows the last log lines.
if launchctl list | grep -q com.tradingbot; then
  PID=$(launchctl list | awk '/com.tradingbot/{print $1}')
  [ "$PID" != "-" ] && echo "RUNNING (pid $PID) - dashboard http://localhost:8000" || echo "INSTALLED but not running right now (restarting?)"
else
  echo "NOT INSTALLED - run: bash scripts/install_mac.sh"
fi
echo "--- last 15 log lines ---"
tail -15 "$HOME/tradingbot-service/logs/bot.log" 2>/dev/null
