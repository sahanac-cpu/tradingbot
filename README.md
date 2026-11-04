# Game-theory paper-trading bot

Rules from a "trading is poker" day-trading talk, coded as a 1-minute-bar strategy.
See `bot/strategy.py` for how each rule maps to code.

```bash
python -m bot.simulate                 # offline test on synthetic data (no keys)
python -m bot.simulate my_bars.csv     # your own bars: t,o,h,l,c,v
python -m bot.live_alpaca SPY 10       # Alpaca *paper* account, needs APCA_API_KEY_ID/SECRET
```

The synthetic results don't count as evidence: the generator puts in the same
patterns the strategy looks for. Test on real historical bars before you believe anything.
Paper trading only.

## Real-time paper bot (fake money, no account needed)

```bash
python -m bot.run SPY QQQ AAPL          # live Yahoo 1-min data, $100k fake cash
python -m bot.run SPY --replay          # replay today's bars now (works after hours)
python -m bot.run SPY --feed alpaca     # Alpaca IEX data instead (APCA_API_KEY_ID/SECRET)
```
Options: `--cash`, `--risk` (default 0.005 = 0.5% of equity per trade), `--max-loss` (0.02 daily stop).
Fills, P&L and equity are logged to `trades.csv`. Positions are closed at 15:50 ET.
