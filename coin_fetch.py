import requests, pandas as pd
from datetime import datetime, timezone

PAIRS = ["BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","TRXUSDT","DOGEUSDT","ADAUSDT"]
OUT_FILE = f"coin_fetch {datetime.now(timezone.utc).isoformat()}.md"

def rsi(s, n=14):
    d = s.diff(); g = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    l = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100/(1 + g/l)

rows = []
for p in PAIRS:
    for tf in ["1w","1d","4h","1h"]:
        k = requests.get("https://api.binance.com/api/v3/klines",
                         params={"symbol":p,"interval":tf,"limit":250}).json()
        c = pd.DataFrame(k).iloc[:,:5].astype(float)
        cl = c[4]
        prev = cl.iloc[-2]
        hi, lo = c[2], c[3]

        line = (f"{p} {tf} O{c[1].iloc[-1]} H{c[2].iloc[-1]} L{c[3].iloc[-1]} C{cl.iloc[-1]} "
                f"MA7={cl.rolling(7).mean().iloc[-1]:.5f} MA25={cl.rolling(25).mean().iloc[-1]:.5f} "
                f"MA99={cl.rolling(99).mean().iloc[-1]:.5f} RSI={rsi(cl).iloc[-1]:.2f}")
        print(line)

        extra = (f"   chg={100*(cl.iloc[-1]/prev-1):+.2f}% MA200={cl.rolling(200).mean().iloc[-1]:.5f} "
                 f"swingH30={hi.tail(30).max():.5f} swingL30={lo.tail(30).min():.5f} "
                 f"swingH90={hi.tail(90).max():.5f} swingL90={lo.tail(90).min():.5f}")
        print(extra)

        rows.append({
            "Pair": p, "TF": tf,
            "O": c[1].iloc[-1], "H": c[2].iloc[-1], "L": c[3].iloc[-1], "C": cl.iloc[-1],
            "MA7": f"{cl.rolling(7).mean().iloc[-1]:.5f}",
            "MA25": f"{cl.rolling(25).mean().iloc[-1]:.5f}",
            "MA99": f"{cl.rolling(99).mean().iloc[-1]:.5f}",
            "MA200": f"{cl.rolling(200).mean().iloc[-1]:.5f}",
            "RSI": f"{rsi(cl).iloc[-1]:.2f}",
            "Chg%": f"{100*(cl.iloc[-1]/prev-1):+.2f}",
            "SwingH30": f"{hi.tail(30).max():.5f}",
            "SwingL30": f"{lo.tail(30).min():.5f}",
            "SwingH90": f"{hi.tail(90).max():.5f}",
            "SwingL90": f"{lo.tail(90).min():.5f}",
        })

with open(OUT_FILE, "w") as f:
    f.write(f"# Coin Fetch Report\n\nGenerated: {datetime.now(timezone.utc).isoformat()}\n\n")
    cols = ["Pair","TF","O","H","L","C","MA7","MA25","MA99","MA200","RSI",
            "Chg%","SwingH30","SwingL30","SwingH90","SwingL90"]
    f.write("| " + " | ".join(cols) + " |\n")
    f.write("|" + "|".join(["---"] * len(cols)) + "|\n")
    for r in rows:
        f.write("| " + " | ".join(str(r[c]) for c in cols) + " |\n")

print(f"\nWritten to {OUT_FILE}")
