# KXNE SNIPER 🎯

GitHub **combo sniper** with a cyberpunk web dashboard. It generates RANDOM
username combos (min→max length, from a charset you pick) and blasts
`github.com/{username}` through rotating proxies as fast as your license allows.
The moment a combo returns 404, it's logged as an AVAILABLE HIT.

## Run

```bash
pip install -r requirements.txt
python server.py
