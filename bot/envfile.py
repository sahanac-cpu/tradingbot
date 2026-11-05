"""Loads Alpaca keys from ~/.tradingbot.env (written by the Mac installer), so you never
have to paste keys again. The saved file wins over keys typed into the terminal earlier,
because those are often old keys that were since regenerated."""
import os


def load(path=os.path.expanduser("~/.tradingbot.env")):
    if not os.path.exists(path):
        return
    for line in open(path):
        k, _, v = line.strip().partition("=")
        if k and v:
            os.environ[k] = v
