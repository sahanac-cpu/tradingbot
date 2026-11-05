# Setup guide (about 10 minutes)

## 1. Install Python (once)
- Mac: download from https://www.python.org/downloads/ (3.9 or newer) and install.
- Windows: same site; on the first installer screen tick **"Add python.exe to PATH"**.
- Check it worked: open Terminal (Mac) or Command Prompt (Windows) and type `python3 --version` (Windows: `python --version`).

## 2. Download the bot
```
git clone https://github.com/sahanac-cpu/tradingbot.git
cd tradingbot
```
No git? On the GitHub page click **Code > Download ZIP**, unzip it, and `cd` into the folder.

## 3. Try it with local fake money (no account needed)
```
python3 -m bot.run --replay
```
Your browser opens the dashboard at **http://localhost:8000**. `--replay` plays today's bars instantly,
so you can see it work any time. Press `Ctrl+C` in the terminal to stop.

## 4. Create your Alpaca paper account (free, fake money)
1. Go to https://alpaca.markets and click **Sign Up**. Verify your email.
   You do NOT need to fund anything or finish the real-money application for paper trading.
2. Log in. Top-left, make sure the account switcher says **Paper Trading** (not Live).
3. On the paper dashboard home page find **API Keys** (right side) and click **Generate New Keys**
   (or **Regenerate**).
4. Copy the **Key** and the **Secret**. The secret is shown only once - paste both somewhere safe.
5. Optional: under the paper account settings you can reset the fake balance (e.g. $100,000).
6. Crypto: in the paper account, enable crypto trading if Alpaca asks you to accept the crypto agreement.

## 5. Give the keys to the bot
Mac / Linux (same terminal window you'll run the bot in):
```
export APCA_API_KEY_ID=PKxxxxxxxxxxxxxxxx
export APCA_API_SECRET_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```
Windows Command Prompt:
```
set APCA_API_KEY_ID=PKxxxxxxxxxxxxxxxx
set APCA_API_SECRET_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```
Never put the keys in a file you push to GitHub.

## 6. Run it live against your paper account
```
python3 -m bot.run --broker alpaca
```
- Dashboard: **http://localhost:8000** (opens automatically; bookmark it).
- Trades show up in the dashboard AND in Alpaca's paper dashboard under **Orders / Positions**.
- ETFs trade 9:50-15:30 ET on weekdays; BTC/USD and ETH/USD trade 24/7.
- Keep the terminal open and the computer awake (Mac: put `caffeinate -i` before the command).

Choose your own symbols: `python3 -m bot.run --broker alpaca VOO SPY QQQ BTC/USD`
(crypto is written `XXX/USD`; Alpaca supports BTC, ETH, SOL, LTC, AVAX, DOGE and more).

## 7. See every trade and whether it's working
```
python3 -m bot.report --alpaca
```
Lists every trade with entry, exit and P&L, then win rate, profit factor, worst drawdown and a verdict.
It only says "consider a small real-money test" after 40+ trading days, 100+ trades,
profit factor >= 1.3 and a net profit.

## 8. Run it in the background forever (Mac)
So it keeps running and learning with VS Code and the terminal closed:
```
bash scripts/install_mac.sh
```
It asks for your Alpaca paper keys once, then runs as a background service: it starts when you
log in, restarts itself if it crashes, and keeps the Mac awake. Its brain (`model.json`) keeps
learning across restarts.
- Is it running? `bash ~/tradingbot-service/scripts/status.sh`
- Dashboard: http://localhost:8000
- Get new code + restart: `bash scripts/update_mac.sh`
- Stop it: `bash ~/tradingbot-service/scripts/uninstall_mac.sh`
- Changed your keys: `bash scripts/install_mac.sh --new-keys`

It stops only if the Mac is shut down, logged out, or the lid is closed while on battery.
