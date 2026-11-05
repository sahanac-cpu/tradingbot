#!/bin/bash
# Stops the background bot and removes the service (keeps your logs, model and keys).
PLIST="$HOME/Library/LaunchAgents/com.tradingbot.plist"
launchctl unload "$PLIST" 2>/dev/null && rm -f "$PLIST" && echo "stopped and removed" || echo "was not installed"
