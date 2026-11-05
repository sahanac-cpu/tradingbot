#!/bin/bash
# Pulls the latest code into your folder and restarts the background bot with it.
# Keeps the bot's memory (model.json), account and logs.
cd "$(dirname "$0")/.." && git pull && bash scripts/install_mac.sh
