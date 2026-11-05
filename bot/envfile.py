"""Loads Alpaca keys from ~/.tradingbot.env (written by the Mac installer) when the
terminal doesn't already have them, so you never have to paste keys again."""
import os


def load(path=os.path.expanduser("~/.tradingbot.env")):
    if os.environ.get("APCA_API_KEY_ID") or not os.path.exists(path):
        return
    for line in open(path):
        k, _, v = line.strip().partition("=")
        if k and v:
            os.environ.setdefault(k, v)
