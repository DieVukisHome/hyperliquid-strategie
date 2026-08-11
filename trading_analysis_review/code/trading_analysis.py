#!/usr/bin/env python3
"""
Tägliche Trading-Analyse — 08:00 UTC+2 (Pre-UK-Session)
BTC + aktive Hyperliquid-Positionen
Datenquellen: Binance, Kiyotaka, TBD (HyblockCapital), Hyperliquid
Analyse via OpenRouter (Claude), Ergebnis → Telegram + Datei
"""

import os, json, time, urllib.request, urllib.parse, urllib.error, math, sys
from datetime import datetime, timedelta

# ── Credentials ──────────────────────────────────────────────────────────────
_env = os.path.expanduser("~/.hermes/.env")
if os.path.exists(_env):
    with open(_env) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

TG_TOKEN      = os.environ["TELEGRAM_BOT_TOKEN"]
TG_CHAT       = os.environ.get("TELEGRAM_HOME_CHANNEL") or os.environ["TELEGRAM_ALLOWED_USERS"]
OPENROUTER_KEY= os.environ["OPENROUTER_API_KEY"]
KIYOTAKA_KEY  = os.environ.get("KIYOTAKA_API_KEY", "")
TBD_TOKEN     = os.environ.get("TBD_TOKEN", "")
HL_WALLET     = "0xF53a18caAFc231C98552D8de2BEdb0F5e2Bb19d5"
TBD_BASE      = "https://hyblock-proxy-api.tradetravelchill.club"
OUT_DIR       = os.path.expanduser("~/.hermes/trading_analyses")
os.makedirs(OUT_DIR, exist_ok=True)

# ── Helpers ───────────────────────────────────────────────────────────────────
def get(url, headers=None, timeout=15):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    except Exception as e:
        return {"_error": str(e)}

def post(url, body, headers=None, timeout=15):
    data = json.dumps(body).encode()
    h = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    try:
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    except Exception as e:
        return {"_error": str(e)}

def tg(text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": TG_CHAT, "text": text, "parse_mode": "HTML"}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(url, data=data, method="POST"), timeout=10)
    except Exception as e:
        print(f"TG error: {e}")


def tg_photo(png_bytes, caption=""):
    """sendPhoto (multipart/form-data) — Telegram-Limit: caption 1024 Zeichen."""
    import uuid
    boundary = f"----hermes{uuid.uuid4().hex}"
    caption = (caption or "")[:1024]
    parts = []
    for k, v in (("chat_id", TG_CHAT), ("caption", caption), ("parse_mode", "HTML")):
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    parts.append(
        (f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; "
         f"filename=\"chart.png\"\r\nContent-Type: image/png\r\n\r\n").encode()
        + png_bytes + b"\r\n"
        + f"--{boundary}--\r\n".encode()
    )
    body = b"".join(parts)
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
    req = urllib.request.Request(url, data=body, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        urllib.request.urlopen(req, timeout=20).read()
        return True
    except Exception as e:
        print(f"TG photo error: {e}")
        return False


def ema_series(prices, n):
    """EMA als komplette Serie (nicht nur letzter Wert) — für Chart-Overlay."""
    if not prices:
        return []
    n = min(n, len(prices))
    k = 2 / (n + 1)
    e = prices[0]
    out = [e]
    for p in prices[1:]:
        e = p * k + e * (1 - k)
        out.append(e)
    return out


def parse_setup_cards(text):
    """Extrahiert SETUP-CARD(s) aus Claude-Analyse-Text.
    Return: Liste von dicts mit bias, entry_lo, entry_hi, sl, tp1, tp2 (optional), trigger."""
    import re
    setups = []
    if not text:
        return setups
    # Blockweise ab BIAS bis (Leerzeile+Doppelzeile / nächstes BIAS / Ende)
    # Struktur ist: BIAS ... TRIGGER ... ENTRY-ZONE ... STOP-LOSS ... TP1 ... [TP2]
    pat = re.compile(
        r"BIAS\s*[:*\s]+\**\s*\[?(?P<bias>[A-Za-zÄÖÜäöü\- ]{3,30}?)\]?\s*\n"
        r"(?:.*?TRIGGER\s*[:*\s]+\**\s*(?P<trigger>[^\n]+))?"
        r".*?ENTRY[- ]?ZONE\s*[:*\s]+\**\s*\[?\$?(?P<e1>[\d,]+(?:\.\d+)?)\s*[-–—to]+\s*\$?(?P<e2>[\d,]+(?:\.\d+)?)"
        r".*?STOP[- ]?LOSS\s*[:*\s]+\**\s*\$?(?P<sl>[\d,]+(?:\.\d+)?)"
        r".*?TP1\s*[:*\s]+\**\s*\$?(?P<tp1>[\d,]+(?:\.\d+)?)"
        r"(?:.*?TP2\s*[:*\s]+\**\s*\$?(?P<tp2>[\d,]+(?:\.\d+)?))?",
        re.IGNORECASE | re.DOTALL,
    )
    for m in pat.finditer(text):
        d = m.groupdict()
        try:
            s = {
                "bias": (d["bias"] or "").strip().lower(),
                "entry_lo": min(float(d["e1"].replace(",", "")), float(d["e2"].replace(",", ""))),
                "entry_hi": max(float(d["e1"].replace(",", "")), float(d["e2"].replace(",", ""))),
                "sl": float(d["sl"].replace(",", "")),
                "tp1": float(d["tp1"].replace(",", "")),
                "tp2": float(d["tp2"].replace(",", "")) if d.get("tp2") else None,
                "trigger": (d.get("trigger") or "").strip()[:120],
            }
            setups.append(s)
        except (ValueError, TypeError):
            continue
    return setups


def _session_vwap_series(candles):
    """Rolling Session-VWAP — Reset bei jeder Mitternacht (Server-Lokalzeit).
    Return: Liste (len == len(candles)) mit VWAP-Wert pro Kerze."""
    out = []
    cum_pv = 0.0; cum_v = 0.0
    last_day = None
    for c in candles:
        dt = datetime.fromtimestamp(int(c[0]) / 1000)
        day = dt.date()
        if last_day is None or day != last_day:
            cum_pv = 0.0; cum_v = 0.0
            last_day = day
        h, l, cl, v = float(c[2]), float(c[3]), float(c[4]), float(c[5])
        tp = (h + l + cl) / 3
        cum_pv += tp * v
        cum_v += v
        out.append(cum_pv / cum_v if cum_v > 0 else float("nan"))
    return out


def _vector_colors(candles, avg_n=10, rising=1.5, climax=2.0):
    """PVSRA-Tiers:
      Climax Bull (Vol ≥ climax·Ø): grün-neon
      Climax Bear:                  rot-neon
      Rising  Bull (Vol ≥ rising·Ø): blau
      Rising  Bear:                  violett
      Sonst None (Default-Style)."""
    vols = [float(c[5]) for c in candles]
    cols = [None] * len(candles)
    for i in range(len(candles)):
        if i < avg_n:
            continue
        avg_v = sum(vols[i-avg_n:i]) / avg_n
        if avg_v <= 0 or vols[i] < rising * avg_v:
            continue
        o, cl = float(candles[i][1]), float(candles[i][4])
        spread = float(candles[i][2]) - float(candles[i][3])
        if abs(cl - o) < spread * 0.3:
            continue  # Doji
        is_climax = vols[i] >= climax * avg_v
        is_bull = cl > o
        if is_climax:
            cols[i] = "#00ff88" if is_bull else "#ff2b2b"
        else:
            cols[i] = "#2b8aff" if is_bull else "#c04dff"
    return cols


def parse_critical_zones(text):
    """Aus 'Kritische Zonen'-Abschnitt Preise + Label + oben/unten extrahieren.
    Return: Liste von {price, label, above}."""
    import re
    zones = []
    if not text:
        return zones
    m = re.search(
        r"(?:Kritische[nr]?\s+Zonen)[^\n]*\n(.+?)"
        r"(?=\n\s*(?:\**\s*)?(?:5\.|6\.|7\.|INTRADAY|Offene|Makro|#{2,}|─{3,}|-{3,}|═{3,})|\Z)",
        text, re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return zones
    section = m.group(1)
    for line in section.split("\n"):
        ll = line.lower()
        above = ("oben" in ll) or ("über" in ll and "unter" not in ll) or "↑" in line
        below = ("unten" in ll) or ("unter" in ll and "über" not in ll) or "↓" in line
        pm = re.search(r"\$?([\d]{2,3}[,.]?[\d]{3}(?:\.\d+)?)", line)
        lm = re.search(r"\(([^)]{2,40})\)", line)
        if not pm:
            continue
        try:
            price = float(pm.group(1).replace(",", ""))
        except ValueError:
            continue
        zones.append({
            "price": price,
            "label": (lm.group(1) if lm else "").strip(),
            "above": True if above else (False if below else None),
        })
    return zones[:6]


def _swing_points(candles, lookback=2):
    """Fractal-Swing-Detection: idx ist Swing-High wenn High > alle N vor+nach.
    Return: Liste von (idx, price, 'H'|'L')."""
    swings = []
    highs = [float(c[2]) for c in candles]
    lows  = [float(c[3]) for c in candles]
    for i in range(lookback, len(candles) - lookback):
        h_ok = all(highs[i] > highs[i-k] for k in range(1, lookback+1)) and \
               all(highs[i] > highs[i+k] for k in range(1, lookback+1))
        l_ok = all(lows[i]  < lows[i-k]  for k in range(1, lookback+1)) and \
               all(lows[i]  < lows[i+k]  for k in range(1, lookback+1))
        if h_ok: swings.append((i, highs[i], "H"))
        if l_ok: swings.append((i, lows[i],  "L"))
    return swings


def render_chart_png(raw, coin="BTC", n_candles=72, setups=None, interval="1h",
                     zones=None, mark_vectors=True):
    """Kerzenchart mit EMA20/50/200 + PDH/PDL/PDC/WO/VWAP + Vector-Kerzen + Krit.Zonen.
    interval: '1h' (HTF-Kontext) oder '15m' (Setup-Detail).
    setups: Liste {bias, entry_lo, entry_hi, sl, tp1, tp2} — Setup-Overlay (nur 15m sinnvoll).
    zones:  Liste {price, label, above} — kritische Zonen aus Analyse, dünne violette Linien.
    mark_vectors: PVSRA-Vector-Kerzen bunt einfärben (cyan/magenta).
    Return: PNG bytes oder None bei Fehler."""
    try:
        import io
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import mplfinance as mpf
        import pandas as pd
    except Exception as e:
        print(f"chart: import failed: {e}")
        return None

    key = "ohlcv_15m_" if interval == "15m" else "ohlcv_1h_"
    c_all = raw.get(f"{key}{coin}", [])
    if not isinstance(c_all, list) or len(c_all) < 30:
        print(f"chart: keine {interval}-Daten für {coin}")
        return None

    closes_full = [float(x[4]) for x in c_all]
    e20_full = ema_series(closes_full, 20)
    e50_full = ema_series(closes_full, 50)
    e200_full = ema_series(closes_full, 200)

    slice_ = c_all[-n_candles:]
    e20 = e20_full[-n_candles:]
    e50 = e50_full[-n_candles:]
    e200 = e200_full[-n_candles:]

    df = pd.DataFrame({
        "Date":  [pd.to_datetime(int(k[0]), unit="ms") for k in slice_],
        "Open":  [float(k[1]) for k in slice_],
        "High":  [float(k[2]) for k in slice_],
        "Low":   [float(k[3]) for k in slice_],
        "Close": [float(k[4]) for k in slice_],
        "Volume":[float(k[5]) for k in slice_],
    }).set_index("Date")

    price = float(slice_[-1][4])
    hlines = {}
    hcolors = []
    hstyles = []
    hlabels = []

    c1d = raw.get(f"ohlcv_1d_{coin}", [])
    if isinstance(c1d, list) and len(c1d) >= 2:
        pdh = float(c1d[-2][2]); pdl = float(c1d[-2][3]); pdc = float(c1d[-2][4])
        hlines[f"PDH {pdh:,.0f}"] = pdh; hcolors.append("#ff6b6b"); hstyles.append("--"); hlabels.append("PDH")
        hlines[f"PDL {pdl:,.0f}"] = pdl; hcolors.append("#51cf66"); hstyles.append("--"); hlabels.append("PDL")
        hlines[f"PDC {pdc:,.0f}"] = pdc; hcolors.append("#adb5bd"); hstyles.append(":");  hlabels.append("PDC")

    c1w = raw.get(f"ohlcv_1w_{coin}", [])
    if isinstance(c1w, list) and c1w:
        wo = float(c1w[-1][1])
        hlines[f"WO {wo:,.0f}"] = wo; hcolors.append("#ffa94d"); hstyles.append("-."); hlabels.append("WO")

    # VWAP kommt weiter unten als rollierende Serie (addplot), nicht als hline.

    addplots = [
        mpf.make_addplot(e20, color="#4dabf7", width=1.0),
        mpf.make_addplot(e50, color="#ffd43b", width=1.0),
        mpf.make_addplot(e200, color="#ff8787", width=1.2),
    ]

    # Rolling Session-VWAP (reset bei Mitternacht) — Serie, nicht horizontale Linie
    vwap_full = _session_vwap_series(c_all)
    vwap_slice = vwap_full[-n_candles:]
    if any(not math.isnan(v) for v in vwap_slice):
        addplots.append(mpf.make_addplot(vwap_slice, color="#b197fc",
            width=1.1, linestyle="--"))

    # Swing-Marker (nur auf 15m für Setup-Klarheit) — letzte 6 Highs / 6 Lows
    swing_high_y = [float("nan")] * len(slice_)
    swing_low_y  = [float("nan")] * len(slice_)
    if interval == "15m":
        sw = _swing_points(slice_, lookback=2)
        highs = [(i, y) for i, y, t in sw if t == "H"][-6:]
        lows  = [(i, y) for i, y, t in sw if t == "L"][-6:]
        for i, y in highs: swing_high_y[i] = y
        for i, y in lows:  swing_low_y[i]  = y
        if any(not math.isnan(v) for v in swing_high_y):
            addplots.append(mpf.make_addplot(swing_high_y, type="scatter",
                markersize=60, marker="v", color="#ff8787"))
        if any(not math.isnan(v) for v in swing_low_y):
            addplots.append(mpf.make_addplot(swing_low_y, type="scatter",
                markersize=60, marker="^", color="#51cf66"))

    hline_cfg = dict(
        hlines=list(hlines.values()),
        colors=hcolors, linestyle=hstyles, linewidths=[0.9] * len(hlines),
    )

    span_h = n_candles if interval == "1h" else n_candles * 0.25  # 15m = 0.25h
    title = f"{coin}/USDT · {interval} · letzte {span_h:.0f}h · ${price:,.0f} · {time.strftime('%d.%m %H:%M')}"
    buf = io.BytesIO()
    # Dark-Theme (PVSRA-Look): dunkelblauer Grund, dimm-grün/rot als Default,
    # Vector-Kerzen (neon/blau/violett) leuchten dann heraus.
    mc = mpf.make_marketcolors(
        up="#f5f5f5", down="#7a7a7a",
        edge={"up": "#f5f5f5", "down": "#7a7a7a"},
        wick={"up": "#a0a0a0", "down": "#a0a0a0"},
        volume={"up": "#f5f5f5", "down": "#7a7a7a"},
    )
    style = mpf.make_mpf_style(
        base_mpf_style="nightclouds",
        marketcolors=mc,
        facecolor="#0d1117", edgecolor="#30363d",
        gridcolor="#21262d", gridstyle=":",
        figcolor="#0d1117",
        rc={"axes.labelcolor": "#c9d1d9", "text.color": "#c9d1d9",
            "xtick.color": "#c9d1d9", "ytick.color": "#c9d1d9",
            "axes.edgecolor": "#30363d", "axes.titlecolor": "#f0f6fc"},
    )
    mpf_kwargs = dict(
        type="candle", style=style,
        addplot=addplots, volume=True, hlines=hline_cfg,
        title=title, ylabel="Preis", ylabel_lower="Vol",
        figsize=(11, 7), tight_layout=True,
        returnfig=True,
    )
    if mark_vectors:
        vc = _vector_colors(slice_)
        if any(c is not None for c in vc):
            mpf_kwargs["marketcolor_overrides"] = vc
    try:
        fig, axes = mpf.plot(df, **mpf_kwargs)
        ax0 = axes[0]
        from matplotlib.transforms import blended_transform_factory
        trans = blended_transform_factory(ax0.transAxes, ax0.transData)

        # HLine-Labels (PDH/PDL/PDC/WO) am rechten Rand
        for lbl, y, col in zip(hlabels, list(hlines.values()), hcolors):
            ax0.text(1.005, y, f" {lbl}", va="center", ha="left", fontsize=7,
                     color=col, transform=trans, fontweight="bold")

        # VWAP-Label am rechten Rand (letzter Wert der Serie)
        last_vwap = next((v for v in reversed(vwap_slice) if not math.isnan(v)), None)
        if last_vwap is not None:
            ax0.text(1.005, last_vwap, f" VWAP {last_vwap:,.0f}",
                     va="center", ha="left", fontsize=7,
                     color="#b197fc", transform=trans, fontweight="bold")

        # Kritische Zonen aus Analyse — violette gepunktete Linien mit Label
        for z in (zones or []):
            if any(abs(z["price"] - y) / max(price, 1) < 0.001 for y in hlines.values()):
                continue
            ax0.axhline(z["price"], color="#b197fc", linestyle=":",
                        linewidth=0.9, alpha=0.7, zorder=0)
            arrow = "↑" if z["above"] else ("↓" if z["above"] is False else "·")
            lbl = f" {arrow}Z {z['price']:,.0f}"
            if z["label"]:
                lbl += f" ({z['label'][:22]})"
            ax0.text(1.005, z["price"], lbl, va="center", ha="left", fontsize=6,
                     color="#b197fc", transform=trans, style="italic")

        # Setup-Overlay (Entry-Band, SL, TPs) — Farben für Dark-BG
        for s in (setups or []):
            b = s.get("bias", "")
            is_long = ("long" in b or "bull" in b) and "watch" not in b
            is_short = ("short" in b or "bear" in b) and "watch" not in b
            zone_col = "#51cf66" if is_long else "#ff6b6b" if is_short else "#adb5bd"
            emid = (s["entry_lo"] + s["entry_hi"]) / 2

            ax0.axhspan(s["entry_lo"], s["entry_hi"], alpha=0.22,
                        color=zone_col, zorder=0)
            ax0.text(0.01, emid, f" Entry {emid:,.0f} ({b.upper() or 'SETUP'}) ",
                     va="center", ha="left", fontsize=8, fontweight="bold",
                     color="#0d1117", transform=trans,
                     bbox=dict(boxstyle="round,pad=0.25", facecolor=zone_col,
                               edgecolor="none", alpha=0.95))
            ax0.axhline(s["sl"], color="#ff6b6b", linestyle="--", linewidth=1.4, zorder=1)
            ax0.text(1.005, s["sl"], f" SL {s['sl']:,.0f}", va="center", ha="left",
                     fontsize=8, color="#ff6b6b", transform=trans, fontweight="bold")
            ax0.axhline(s["tp1"], color="#51cf66", linestyle="--", linewidth=1.4, zorder=1)
            ax0.text(1.005, s["tp1"], f" TP1 {s['tp1']:,.0f}", va="center", ha="left",
                     fontsize=8, color="#51cf66", transform=trans, fontweight="bold")
            if s.get("tp2"):
                ax0.axhline(s["tp2"], color="#51cf66", linestyle="-.", linewidth=1.4, zorder=1)
                ax0.text(1.005, s["tp2"], f" TP2 {s['tp2']:,.0f}", va="center", ha="left",
                         fontsize=8, color="#51cf66", transform=trans, fontweight="bold")

        fig.savefig(buf, dpi=110, bbox_inches="tight", format="png")
        plt.close(fig)
    except Exception as e:
        print(f"chart: mpf.plot failed: {e}")
        plt.close("all")
        return None
    buf.seek(0)
    return buf.getvalue()

def ema(prices, n):
    n = min(n, len(prices))
    k = 2/(n+1); e = prices[0]
    for p in prices[1:]: e = p*k + e*(1-k)
    return e

def fusd(v):
    return f"${v/1e6:.2f}M" if v >= 1e6 else f"${v/1e3:.1f}K"

def vector_tag(candles, idx, avg_n=10, threshold=1.5):
    """PVSRA Vector Candle: Volumen >= threshold * Ø(letzten avg_n Kerzen) + Body vorhanden"""
    vols = [float(c[5]) for c in candles]
    if idx < avg_n: return ""
    avg_vol = sum(vols[idx-avg_n:idx]) / avg_n
    vol = vols[idx]
    if vol < threshold * avg_vol: return ""
    o, cl = float(candles[idx][1]), float(candles[idx][4])
    body = abs(cl - o)
    spread = float(candles[idx][2]) - float(candles[idx][3])
    if body < spread * 0.3: return ""  # Doji — kein Vector
    return " 🔵VECTOR" if cl > o else " 🔴VECTOR"

def rsi(prices, n=14):
    if len(prices) < n+2: return None
    g, l = [], []
    for i in range(1, len(prices)):
        d = prices[i]-prices[i-1]; g.append(max(d,0)); l.append(max(-d,0))
    ag = sum(g[-n:])/n; al = sum(l[-n:])/n
    for i in range(n, len(g)):
        ag=(ag*(n-1)+g[i])/n; al=(al*(n-1)+l[i])/n
    return 100-100/(1+ag/al) if al else 100.0

# ── Daten holen ───────────────────────────────────────────────────────────────
def fetch_all(coins):
    data = {}
    now = int(time.time())
    from48h_ago = now - 172800

    # Binance OHLCV für jeden Coin
    for coin in coins:
        sym = f"{coin}USDT"
        data[f"ohlcv_4h_{coin}"]  = get(f"https://api.binance.com/api/v3/klines?symbol={sym}&interval=4h&limit=300")
        data[f"ohlcv_1h_{coin}"]  = get(f"https://api.binance.com/api/v3/klines?symbol={sym}&interval=1h&limit=500")
        data[f"ohlcv_15m_{coin}"] = get(f"https://api.binance.com/api/v3/klines?symbol={sym}&interval=15m&limit=100")
        data[f"ohlcv_1d_{coin}"]  = get(f"https://api.binance.com/api/v3/klines?symbol={sym}&interval=1d&limit=200")
        data[f"ohlcv_1w_{coin}"]  = get(f"https://api.binance.com/api/v3/klines?symbol={sym}&interval=1w&limit=100")
        data[f"funding_{coin}"]   = get(f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={sym}&limit=10")
        data[f"oi_{coin}"]        = get(f"https://fapi.binance.com/fapi/v1/openInterest?symbol={sym}")
        data[f"orderbook_{coin}"] = get(f"https://api.binance.com/api/v3/depth?symbol={sym}&limit=500")
        data[f"aggtrades_{coin}"] = get(f"https://api.binance.com/api/v3/aggTrades?symbol={sym}&limit=1000")
        data[f"premium_{coin}"]   = get(f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={sym}")

        # Kiyotaka
        if KIYOTAKA_KEY:
            kh = {"X-Kiyotaka-Key": KIYOTAKA_KEY}
            base = f"https://api.kiyotaka.ai/v1/points?exchange=BINANCE_FUTURES&rawSymbol={sym}&interval=HOUR&from={from48h_ago}&period=172800"
            data[f"kiy_liq_{coin}"] = get(f"{base}&type=LIQUIDATION_AGG", kh)
            data[f"kiy_oi_{coin}"]  = get(f"{base}&type=OPEN_INTEREST_AGG", kh)

        # TBD
        if TBD_TOKEN:
            th = {"Authorization": f"Bearer {TBD_TOKEN}", "Accept": "application/json"}
            c = coin  # BTC, ETH etc.
            data[f"tbd_heat_1d_{coin}"]  = get(f"{TBD_BASE}/v2/liquidationHeatmap?exchange=BINANCE&lookback=1d&coin={c}", th)
            data[f"tbd_heat_3d_{coin}"]  = get(f"{TBD_BASE}/v2/liquidationHeatmap?exchange=BINANCE&lookback=3d&coin={c}", th)
            data[f"tbd_heat_7d_{coin}"]  = get(f"{TBD_BASE}/v2/liquidationHeatmap?exchange=BINANCE&lookback=7d&coin={c}", th)
            data[f"tbd_heat_1m_{coin}"]  = get(f"{TBD_BASE}/v2/liquidationHeatmap?exchange=BINANCE&lookback=1m&coin={c}", th)
            data[f"tbd_levels_{coin}"]   = get(f"{TBD_BASE}/v2/liquidationLevels?exchange=BINANCE&leverage=all&position=all&coin={c}", th)
            data[f"tbd_cumul_{coin}"]    = get(f"{TBD_BASE}/v2/cumulativeLiqLevel?exchange=BINANCE&coin={c}", th)
            data[f"tbd_funding_{coin}"]  = get(f"{TBD_BASE}/v2/fundingRate?exchange=BINANCE&timeframe=1h&coin={c}&sort=asc&aggregationType=sum&limit=20", th)
            data[f"tbd_retail_ls_{coin}"] = get(f"{TBD_BASE}/v2/trueRetailLongShort?exchange=BINANCE&timeframe=1h&coin={c}&sort=desc&limit=10", th)
            data[f"tbd_oi_delta_{coin}"]  = get(f"{TBD_BASE}/v2/openInterestDelta?exchange=BINANCE&timeframe=1h&coin={c}&sort=desc&limit=10", th)
            data[f"tbd_ba_delta_{coin}"]  = get(f"{TBD_BASE}/v2/bidAskDelta?exchange=BINANCE&timeframe=1h&coin={c}&sort=desc&limit=10", th)

    # TBD globale Daten (einmal)
    if TBD_TOKEN:
        th = {"Authorization": f"Bearer {TBD_TOKEN}", "Accept": "application/json"}
        data["tbd_forex"] = get(f"{TBD_BASE}/forex", th)

    # Hyperliquid Positionen
    hl = post("https://api.hyperliquid.xyz/info", {"type": "clearinghouseState", "user": HL_WALLET})
    data["hl_positions"] = hl

    return data

# ── Daten → kompaktes Text-Summary ───────────────────────────────────────────
def summarize(raw, coins):
    lines = []
    ts = time.strftime("%Y-%m-%d %H:%M UTC+2", time.localtime())
    lines.append(f"TRADING ANALYSE — {ts}\n")

    for coin in coins:
        lines.append(f"\n{'='*50}")
        lines.append(f"  {coin}/USDT")
        lines.append(f"{'='*50}")

        c4h = raw.get(f"ohlcv_4h_{coin}", [])
        c1d = raw.get(f"ohlcv_1d_{coin}", [])
        c1w = raw.get(f"ohlcv_1w_{coin}", [])

        if not isinstance(c4h, list) or not c4h:
            lines.append("  [Binance Daten nicht verfügbar]"); continue

        price = float(c4h[-1][4])
        closes_4h = [float(x[4]) for x in c4h]
        closes_1d = [float(x[4]) for x in c1d] if isinstance(c1d, list) else []
        closes_1w = [float(x[4]) for x in c1w] if isinstance(c1w, list) else []

        lines.append(f"Preis: ${price:,.4f}" if price < 100 else f"Preis: ${price:,.0f}")
        lines.append(f"4H: EMA20={ema(closes_4h,20):,.4f} EMA50={ema(closes_4h,50):,.4f} EMA200={ema(closes_4h,200):,.4f} RSI={rsi(closes_4h):.1f}" if rsi(closes_4h) and price < 100 else
                     f"4H: EMA20={ema(closes_4h,20):,.0f} EMA50={ema(closes_4h,50):,.0f} EMA200={ema(closes_4h,200):,.0f} RSI={rsi(closes_4h):.1f}" if rsi(closes_4h) else
                     f"4H: EMA20={ema(closes_4h,20):,.0f} EMA200={ema(closes_4h,200):,.0f}")
        if closes_1d:
            r = rsi(closes_1d)
            lines.append(f"Daily: EMA20={ema(closes_1d,20):,.4f} EMA50={ema(closes_1d,50):,.4f} RSI={r:.1f}" if r and price < 100 else
                         f"Daily: EMA20={ema(closes_1d,20):,.0f} EMA50={ema(closes_1d,50):,.0f} RSI={r:.1f}" if r else
                         f"Daily: EMA20={ema(closes_1d,20):,.0f}")
        if closes_1w:
            r = rsi(closes_1w)
            lines.append(f"Weekly: EMA20={ema(closes_1w,20):,.0f} RSI={r:.1f}" if r else f"Weekly: EMA20={ema(closes_1w,20):,.0f}")

        # Letzte 3x 4H Kerzen + Vector-Tag
        lines.append("Letzte 3x 4H:")
        for i, c in enumerate(c4h[-3:], start=len(c4h)-3):
            o,h,l,cl = float(c[1]),float(c[2]),float(c[3]),float(c[4])
            t = time.strftime("%d.%m %H:%M", time.localtime(c[0]/1000))
            vtag = vector_tag(c4h, i)
            lines.append(f"  {t}  {(cl-o)/o*100:+.2f}%  H={h:,.3f} L={l:,.3f}{vtag}")

        # 1H Vector-Kerzen (letzte 8) + EMAs + RSI (kurzfristig wichtigster TF)
        c1h = raw.get(f"ohlcv_1h_{coin}", [])
        if isinstance(c1h, list) and len(c1h) > 10:
            closes_1h = [float(x[4]) for x in c1h]
            e20_1h, e50_1h, e200_1h = ema(closes_1h,20), ema(closes_1h,50), ema(closes_1h,200)
            r1h = rsi(closes_1h)
            pos = "über" if price > e200_1h else "unter"
            if price < 100:
                lines.append(f"1H: EMA20={e20_1h:,.4f} EMA50={e50_1h:,.4f} EMA200={e200_1h:,.4f} RSI={r1h:.1f} (Preis {pos} EMA200)")
            else:
                lines.append(f"1H: EMA20={e20_1h:,.0f} EMA50={e50_1h:,.0f} EMA200={e200_1h:,.0f} RSI={r1h:.1f} (Preis {pos} EMA200)")
            lines.append("Letzte 8x 1H:")
            for i, c in enumerate(c1h[-8:], start=len(c1h)-8):
                o,h,l,cl = float(c[1]),float(c[2]),float(c[3]),float(c[4])
                t = time.strftime("%d.%m %H:%M", time.localtime(c[0]/1000))
                vtag = vector_tag(c1h, i)
                lines.append(f"  {t}  {(cl-o)/o*100:+.2f}%  H={h:,.3f} L={l:,.3f}{vtag}" if price<100 else
                             f"  {t}  {(cl-o)/o*100:+.2f}%  H={h:,.0f} L={l:,.0f}{vtag}")

        # 15M: EMA-Stack + RSI + Struktur + 8 Kerzen mit H/L
        c15m = raw.get(f"ohlcv_15m_{coin}", [])
        if isinstance(c15m, list) and len(c15m) > 10:
            closes_15m = [float(x[4]) for x in c15m]
            e20_15, e50_15, e200_15 = ema(closes_15m,20), ema(closes_15m,50), ema(closes_15m,200)
            r15 = rsi(closes_15m)
            pos15 = "über" if price > (e200_15 or 0) else "unter"
            fmt = ",.4f" if price < 100 else ",.0f"
            e_line = f"15M: EMA20={e20_15:{fmt}} EMA50={e50_15:{fmt}}"
            if e200_15:
                e_line += f" EMA200={e200_15:{fmt}} (Preis {pos15} EMA200)"
            if r15:
                e_line += f" RSI={r15:.1f}"
            lines.append(e_line)

            # Struktur: HH/HL vs LH/LL aus letzten 8 Kerzen (Highs + Lows)
            last8 = c15m[-8:]
            highs = [float(k[2]) for k in last8]
            lows  = [float(k[3]) for k in last8]
            # trend der 4 letzten highs/lows
            def _trend(seq):
                if len(seq) < 3: return "?"
                up = sum(1 for i in range(1,len(seq)) if seq[i] > seq[i-1])
                dn = sum(1 for i in range(1,len(seq)) if seq[i] < seq[i-1])
                if up >= len(seq)-2: return "↑"
                if dn >= len(seq)-2: return "↓"
                return "→"
            th, tl = _trend(highs[-4:]), _trend(lows[-4:])
            struct = "HH/HL (Uptrend)" if th=="↑" and tl=="↑" else \
                     "LH/LL (Downtrend)" if th=="↓" and tl=="↓" else \
                     "HH/LL (Expansion)" if th=="↑" and tl=="↓" else \
                     "LH/HL (Compression)" if th=="↓" and tl=="↑" else \
                     f"gemischt (H:{th} L:{tl})"
            range_pct = (max(highs)-min(lows))/price*100
            lines.append(f"15M Struktur (letzte 8): {struct} | Range={range_pct:.2f}%")

            lines.append("Letzte 8x 15M:")
            for i, c in enumerate(last8, start=len(c15m)-8):
                o,h,l,cl = float(c[1]),float(c[2]),float(c[3]),float(c[4])
                t = time.strftime("%H:%M", time.localtime(c[0]/1000))
                vtag = vector_tag(c15m, i)
                if price < 100:
                    lines.append(f"  {t}  {(cl-o)/o*100:+.2f}%  H={h:,.4f} L={l:,.4f}{vtag}")
                else:
                    lines.append(f"  {t}  {(cl-o)/o*100:+.2f}%  H={h:,.0f} L={l:,.0f}{vtag}")

        # Funding
        fr = raw.get(f"funding_{coin}", [])
        if isinstance(fr, list) and fr:
            rates = [float(x['fundingRate'])*100 for x in fr]
            lines.append(f"Funding: {rates[-1]:+.4f}% (Ø: {sum(rates)/len(rates):+.4f}%)")

        # OI
        oi = raw.get(f"oi_{coin}", {})
        if isinstance(oi, dict) and "openInterest" in oi:
            oi_val = float(oi["openInterest"])
            lines.append(f"OI: {oi_val:,.0f} {coin} = {fusd(oi_val*price)}")

        # Spot/Perp Basis
        prem = raw.get(f"premium_{coin}", {})
        if isinstance(prem, dict) and "markPrice" in prem and "indexPrice" in prem:
            mark = float(prem["markPrice"])
            index = float(prem["indexPrice"])
            basis = (mark - index) / index * 100
            bias = "Perp Premium (Long-Bias)" if basis > 0.02 else "Perp Discount (Short-Bias)" if basis < -0.02 else "neutral"
            lines.append(f"Spot/Perp Basis: {basis:+.4f}% ({bias})  Mark={mark:g} Spot={index:g}")

        # Order Book Depth
        ob = raw.get(f"orderbook_{coin}", {})
        if isinstance(ob, dict) and "bids" in ob and "asks" in ob:
            bids = [(float(p), float(q)) for p, q in ob["bids"]]
            asks = [(float(p), float(q)) for p, q in ob["asks"]]
            bid_1pct = sum(p*q for p,q in bids if p >= price*0.99)
            ask_1pct = sum(p*q for p,q in asks if p <= price*1.01)
            ratio = bid_1pct/ask_1pct if ask_1pct else 0
            top_bids = sorted(bids, key=lambda x: x[0]*x[1], reverse=True)[:3]
            top_asks = sorted(asks, key=lambda x: x[0]*x[1], reverse=True)[:3]
            lines.append(f"Order Book (±1%): Bids={fusd(bid_1pct)}  Asks={fusd(ask_1pct)}  Ratio={ratio:.2f}")
            for p,q in sorted(top_asks, key=lambda x: x[0]):
                lines.append(f"  Ask ${p:g} — {fusd(p*q)}")
            for p,q in sorted(top_bids, key=lambda x: x[0], reverse=True):
                lines.append(f"  Bid ${p:g} — {fusd(p*q)}")

        # CVD + Large Trades (aggTrades — letzten ~1000 Trades)
        trades = raw.get(f"aggtrades_{coin}", [])
        if isinstance(trades, list) and trades:
            buy_vol = sum(float(t["q"]) for t in trades if not t["m"])
            sell_vol = sum(float(t["q"]) for t in trades if t["m"])
            cvd = buy_vol - sell_vol
            total = buy_vol + sell_vol
            buy_pct = buy_vol/total*100 if total else 50
            mins = (trades[-1]["T"] - trades[0]["T"]) / 60000
            lines.append(f"CVD ({mins:.0f}min): {cvd:+,.2f} {coin} ({fusd(abs(cvd*price))}{'+' if cvd>=0 else '-'})  Buy={buy_pct:.0f}% Sell={100-buy_pct:.0f}%")
            # Top 5 Large Trades
            by_usd = sorted([(float(t["p"])*float(t["q"]), i, t) for i,t in enumerate(trades)], reverse=True)[:5]
            lines.append(f"Large Trades (Top 5):")
            for usd, _, t in by_usd:
                direction = "BUY " if not t["m"] else "SELL"
                ts = time.strftime("%H:%M:%S", time.localtime(t["T"]/1000))
                lines.append(f"  {ts} {direction} {fusd(usd)}")

        # Kiyotaka OI Trend
        koi = raw.get(f"kiy_oi_{coin}", {})
        if isinstance(koi, dict) and koi.get("series"):
            try:
                pts = koi["series"][0].get("points", [])
                if len(pts) >= 2:
                    p0 = pts[0].get("Point", {}); pl = pts[-1].get("Point", {})
                    v0 = p0.get("close", p0.get("value", p0.get("openInterest")))
                    vl = pl.get("close", pl.get("value", pl.get("openInterest")))
                    if v0 is not None and vl is not None:
                        f0 = float(v0); fl = float(vl)
                        lines.append(f"OI 48h: {f0:,.0f} → {fl:,.0f} ({(fl-f0)/f0*100:+.1f}%)")
            except (KeyError, TypeError, ValueError, ZeroDivisionError, IndexError) as e:
                lines.append(f"OI 48h: n/a (parse-error: {e})")

        # Reference Levels: PDH/PDL/PDC + Weekly Open + Session VWAP
        try:
            ref_parts = []
            if len(c1d) >= 2:
                pdh = float(c1d[-2][2]); pdl = float(c1d[-2][3]); pdc = float(c1d[-2][4])
                ref_parts.append(f"PDH=${pdh:,.0f} ({(pdh-price)/price*100:+.2f}%)  PDL=${pdl:,.0f} ({(pdl-price)/price*100:+.2f}%)  PDC=${pdc:,.0f}")
            if c1w:
                wo = float(c1w[-1][1])
                ref_parts.append(f"Weekly Open: ${wo:,.0f} ({(wo-price)/price*100:+.2f}%)")
            # Session VWAP aus 15m-Kerzen seit heute 00:00 UTC+2 (=22:00 UTC gestern)
            fifteen = raw.get(f"ohlcv_15m_{coin}", [])
            if isinstance(fifteen, list) and fifteen:
                now_local = datetime.now()
                midnight_local = datetime(now_local.year, now_local.month, now_local.day, 0, 0, 0)
                # UTC+2 → UTC = local - 2h
                session_start_ms = int((midnight_local - timedelta(hours=2)).timestamp() * 1000)
                session = [k for k in fifteen if k[0] >= session_start_ms]
                if session:
                    pv = sum((float(k[2])+float(k[3])+float(k[4]))/3 * float(k[5]) for k in session)
                    v = sum(float(k[5]) for k in session)
                    if v > 0:
                        vwap = pv/v
                        ref_parts.append(f"Session VWAP (seit 00:00): ${vwap:,.0f} ({(vwap-price)/price*100:+.2f}%)")
            if ref_parts:
                lines.append("Reference Levels:")
                for p in ref_parts:
                    lines.append(f"  {p}")
        except Exception as e:
            lines.append(f"Reference Levels: n/a ({e})")

        # Kiyotaka Liquidationen
        kliq = raw.get(f"kiy_liq_{coin}", {})
        if isinstance(kliq, dict) and kliq.get("series"):
            try:
                buy_total = sum(p.get("Point",{}).get("liquidations",0) for s in kliq["series"] if s.get("id",{}).get("side")=="BUY" for p in s.get("points",[]))
                sell_total = sum(p.get("Point",{}).get("liquidations",0) for s in kliq["series"] if s.get("id",{}).get("side")=="SELL" for p in s.get("points",[]))
                lines.append(f"Kiy Liq 48h: Long={buy_total:.1f}{coin}=${buy_total*price/1e6:.1f}M  Short={sell_total:.1f}{coin}=${sell_total*price/1e6:.1f}M")
            except (KeyError, TypeError, ValueError) as e:
                lines.append(f"Kiy Liq 48h: n/a (parse-error: {e})")

        # TBD Levels — ALLE high + medium leverage (low = Retail-Noise filtern), sortiert nach Preis
        tbd_lev = raw.get(f"tbd_levels_{coin}", {})
        if isinstance(tbd_lev, dict) and "data" in tbd_lev:
            lvls = [l for l in tbd_lev["data"] if l.get("leverage") in ("high", "medium")]
            above = sorted([l for l in lvls if l["price"]>price], key=lambda x: x["price"])
            below = sorted([l for l in lvls if l["price"]<=price], key=lambda x: x["price"], reverse=True)
            lines.append(f"Liq-Levels über Preis (high+medium, {len(above)}):")
            for l in above:
                lines.append(f"  ↑${l['price']:,.0f} +{(l['price']-price)/price*100:.1f}% ${l['size']/1e6:.0f}M {l['side']} {l['leverage']}")
            lines.append(f"Liq-Levels unter Preis (high+medium, {len(below)}):")
            for l in below:
                lines.append(f"  ↓${l['price']:,.0f} -{(price-l['price'])/price*100:.1f}% ${l['size']/1e6:.0f}M {l['side']} {l['leverage']}")

        # TBD Heatmap ALLE Cluster innerhalb ±8% vom Preis, sortiert nach Preis (jedes TF)
        def _fmt_heat_full(hkey, label):
            h = raw.get(f"tbd_heat_{hkey}_{coin}", {})
            if not (isinstance(h, dict) and "data" in h):
                return
            clusters = [x for x in h["data"] if x["size"]>0
                        and abs((x["startingPrice"]-price)/price) <= 0.08]
            clusters.sort(key=lambda x: x["startingPrice"])
            lines.append(f"Heatmap {label} Cluster (±8%, {len(clusters)}):")
            for c_ in clusters:
                d = (c_["startingPrice"]-price)/price*100
                lines.append(f"  {'↑' if d>0 else '↓'}${c_['startingPrice']:,.0f} {d:+.2f}% {c_['side'].upper()} size={c_['size']:.0f}")

        _fmt_heat_full("1d", "1d")
        _fmt_heat_full("3d", "3d")
        _fmt_heat_full("7d", "7d")
        _fmt_heat_full("1m", "1M")

        # TBD Cumulative Delta
        cum = raw.get(f"tbd_cumul_{coin}", {})
        if isinstance(cum, dict) and "data" in cum and cum["data"]:
            d = cum["data"][0]
            delta = d["totalSizeLiquidationDelta"]/1e6
            lines.append(f"Cumul.Delta: ${delta:+.0f}M ({'mehr Longs gelixt' if delta>0 else 'mehr Shorts gelixt'})")

        # TBD Funding (letzte 5h)
        tbd_fr = raw.get(f"tbd_funding_{coin}", {})
        if isinstance(tbd_fr, dict) and "data" in tbd_fr:
            last5 = tbd_fr["data"][-5:]
            fr_vals = [x["fundingRate"] for x in last5]
            lines.append(f"TBD Funding (5h): {', '.join(f'{v:+.4f}%' for v in fr_vals)}")

        # TBD Retail Long/Short % (letzte 10h, neueste zuerst → chronologisch drehen)
        rls = raw.get(f"tbd_retail_ls_{coin}", {})
        if isinstance(rls, dict) and "data" in rls and rls["data"]:
            series = list(reversed(rls["data"]))
            latest = series[-1]
            oldest = series[0]
            trend = latest["longPct"] - oldest["longPct"]
            hist = ", ".join(f"{x['longPct']:.1f}" for x in series)
            lines.append(f"Retail L/S (10h): akt Long {latest['longPct']:.1f}% / Short {latest['shortPct']:.1f}% (Δ Long {trend:+.1f}pp vs vor 10h)")
            lines.append(f"  Verlauf Long%: {hist}")

        # TBD Open Interest Delta (letzte 10h, USD-Millionen)
        oid = raw.get(f"tbd_oi_delta_{coin}", {})
        if isinstance(oid, dict) and "data" in oid and oid["data"]:
            series = list(reversed(oid["data"]))
            total = sum(x["openInterestDelta"] for x in series) / 1e6
            latest = series[-1]["openInterestDelta"] / 1e6
            hist = ", ".join(f"{x['openInterestDelta']/1e6:+.1f}" for x in series)
            lines.append(f"OI-Delta (10h): akt ${latest:+.1f}M, Summe ${total:+.1f}M ({'Aufbau' if total>0 else 'Abbau'})")
            lines.append(f"  Verlauf $M: {hist}")

        # TBD Bid/Ask Delta (Order-Book-Ungleichgewicht, USD-Millionen)
        bad = raw.get(f"tbd_ba_delta_{coin}", {})
        if isinstance(bad, dict) and "data" in bad and bad["data"]:
            series = list(reversed(bad["data"]))
            latest = series[-1]["bidAskDelta"] / 1e6
            avg = sum(x["bidAskDelta"] for x in series) / len(series) / 1e6
            hist = ", ".join(f"{x['bidAskDelta']/1e6:+.1f}" for x in series)
            lines.append(f"Bid/Ask-Delta (10h): akt ${latest:+.1f}M, Ø ${avg:+.1f}M ({'Bids dominieren' if latest>0 else 'Asks dominieren'})")
            lines.append(f"  Verlauf $M: {hist}")

    # Globale Daten
    lines.append(f"\n{'='*50}")
    lines.append("  GLOBAL")
    lines.append(f"{'='*50}")

    # Forex — nur High-Impact der nächsten 24h (in ET, +6h für UTC+2)
    forex = raw.get("tbd_forex", [])
    if isinstance(forex, list):
        hi = [x for x in forex if x.get("impact") == "High"]
        # Sortieren nach Datum-String
        hi_sorted = sorted(hi, key=lambda x: x.get("date",""))
        lines.append("High-Impact Events (ET-Zeit, lokal +6h):")
        for x in hi_sorted[:6]:
            date_display = x["date"][5:16].replace("T"," ")
            fc = f" F={x['forecast']}" if x.get("forecast") else ""
            pr = f" P={x['previous']}" if x.get("previous") else ""
            lines.append(f"  {date_display} ET  {x['country']}  {x['title']}{fc}{pr}")

    # Hyperliquid Positionen
    hl = raw.get("hl_positions", {})
    if isinstance(hl, dict) and "assetPositions" in hl:
        positions = [p for p in hl["assetPositions"] if float(p["position"].get("szi","0")) != 0]
        if positions:
            lines.append(f"\nOffene HL-Positionen ({len(positions)}):")
            for p in positions:
                pos = p["position"]
                coin_p = pos.get("coin","?")
                szi = float(pos.get("szi",0))
                ep = float(pos.get("entryPx",0))
                upnl = float(pos.get("unrealizedPnl",0))
                side = "LONG" if szi > 0 else "SHORT"
                lines.append(f"  {coin_p} {side} sz={abs(szi)} entry=${ep:,.2f} uPnL=${upnl:+.2f}")
        else:
            lines.append("\nKeine offenen HL-Positionen")

    return "\n".join(lines)

# ── Track-Record (Feedback-Loop) ─────────────────────────────────────────────
TRACK_FILE = os.path.join(OUT_DIR, "track_record.json")

def load_track():
    if os.path.exists(TRACK_FILE):
        try:
            with open(TRACK_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"calls": []}

def save_track(t):
    with open(TRACK_FILE, "w") as f:
        json.dump(t, f, indent=2)

def enrich_track(track):
    """Alle Calls ≥24h alt, die noch nicht evaluiert sind: Binance-Preis holen, Return + Bias-Hit."""
    now = datetime.now()
    changed = False
    for call in track.get("calls", []):
        if call.get("outcome_evaluated_at"):
            continue
        try:
            call_dt = datetime.strptime(call["timestamp"], "%Y-%m-%d_%Hh")
        except Exception:
            continue
        if (now - call_dt).total_seconds() < 24*3600:
            continue
        # UTC+2 → UTC
        end_ms = int((call_dt + timedelta(hours=24) - timedelta(hours=2)).timestamp() * 1000)
        start_ms = end_ms - 3600*1000
        k = get(f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1h&startTime={start_ms}&endTime={end_ms}&limit=2")
        if not isinstance(k, list) or not k:
            continue
        close_24h = float(k[-1][4])
        p0 = call.get("price_at")
        if not p0:
            continue
        ret = (close_24h - p0) / p0 * 100
        bias = (call.get("bias") or "").lower()
        hit = None
        if "bull" in bias or bias == "long":
            hit = ret > 0
        elif "bear" in bias or bias == "short":
            hit = ret < 0
        call["price_24h_later"] = round(close_24h, 2)
        call["return_24h_pct"] = round(ret, 2)
        call["bias_hit_24h"] = hit
        call["outcome_evaluated_at"] = now.strftime("%Y-%m-%d %H:%M")
        changed = True
    return changed

def append_call(track, timestamp, price, bias, setup):
    track.setdefault("calls", []).append({
        "timestamp": timestamp,
        "price_at": price,
        "bias": bias,
        "setup_summary": (setup or "")[:120],
        "price_24h_later": None,
        "return_24h_pct": None,
        "bias_hit_24h": None,
        "outcome_evaluated_at": None,
    })
    track["calls"] = track["calls"][-150:]

def format_track_record(track, last_n=10):
    calls = [c for c in track.get("calls", []) if c.get("outcome_evaluated_at")]
    if not calls:
        return "Track Record: noch keine ausgewerteten Calls (System frisch / erste Runs)."
    recent = calls[-last_n:]
    scored = [c for c in recent if c.get("bias_hit_24h") is not None]
    lines = [f"Recent Track Record (letzte {len(recent)} Calls mit 24h-Outcome):"]
    if scored:
        hits = sum(1 for c in scored if c["bias_hit_24h"])
        lines.append(f"  Bias-Hit-Rate: {hits}/{len(scored)} = {hits/len(scored)*100:.0f}%")
    # Detail: letzte 6
    for c in recent[-6:]:
        h = c.get("bias_hit_24h")
        h_str = "✓" if h is True else ("✗" if h is False else "·")
        lines.append(f"  {c['timestamp']}  bias={c.get('bias','?'):<8s}  24h ret={c.get('return_24h_pct',0):+.2f}%  [{h_str}]")
    # Warnungen: 3+ selber Bias in Folge falsch
    tail_wrong = [c for c in scored[-5:] if c.get("bias_hit_24h") is False]
    if len(tail_wrong) >= 3:
        biases = [c.get("bias","") for c in tail_wrong]
        if len(set(biases)) == 1:
            b = biases[0]
            lines.append(f"  ⚠ WARNUNG: {len(tail_wrong)} {b}-Calls in Folge daneben → reflexartige {b}-Antwort JETZT vermeiden")
    # Ø Return by Bias
    from collections import defaultdict
    by_bias = defaultdict(list)
    for c in scored:
        by_bias[c.get("bias","?")].append(c.get("return_24h_pct",0))
    for b, rets in by_bias.items():
        lines.append(f"  Ø 24h ret bei {b}: {sum(rets)/len(rets):+.2f}% (n={len(rets)})")
    return "\n".join(lines)

def extract_bias_setup_from_analysis(analysis_text):
    """Aus Claude-Output Bias + Setup-Line rausziehen."""
    import re
    bias = "unknown"
    for pat in [r"HTF[- ]?Bias[:*\s]+\**\s*(bullish|bearish|neutral|long|short)",
                r"\bBIAS[:*\s]+\**\s*\[?\s*(bullish|bearish|neutral|long|short|neutral-watch)",
                r"^\s*1\.\s*\**HTF[- ]?Bias\**\s*[:\-—]\s*\**\s*(bullish|bearish|neutral)"]:
        m = re.search(pat, analysis_text, re.IGNORECASE | re.MULTILINE)
        if m:
            bias = m.group(1).lower()
            break
    setup = "unknown"
    m2 = re.search(r"BIAS:\s*\[?([^\]\n]{3,80})", analysis_text)
    if m2:
        setup = m2.group(1).strip()
    else:
        m3 = re.search(r"Setup[- ]?Qualit[äa]t[:*\s]+\**\s*([^\n\.]{3,80})", analysis_text)
        if m3:
            setup = m3.group(1).strip()
    return bias, setup


# ── Vorherige Analyse laden (Loop / Self-Review) ────────────────────────────
def load_previous_analysis(current_price=None):
    """Findet neueste vorherige Analyse-Datei, extrahiert Zeit/Preis/Bias/Setup.
    Liefert dict oder None."""
    try:
        import re, glob
        files = sorted(glob.glob(os.path.join(OUT_DIR, "*.md")))
        # Aktuelle Datei (heute+Stunde) ausschließen — die wird gerade geschrieben
        ts_now = time.strftime("%Y-%m-%d_%Hh")
        files = [f for f in files if ts_now not in f and "TAO" not in f]
        if not files:
            return None
        prev = files[-1]
        with open(prev) as f:
            content = f.read()
        # Preis
        m_price = re.search(r"Preis:\s*\$?([\d,]+(?:\.\d+)?)", content)
        prev_price = float(m_price.group(1).replace(",","")) if m_price else None
        # Bias
        m_bias = re.search(r"(?:HTF-)?Bias[:*\s]+\**\s*(bullish|bearish|neutral|long|short)", content, re.IGNORECASE)
        prev_bias = m_bias.group(1).lower() if m_bias else "unknown"
        # Setup-Qualität (grober Match)
        m_setup = re.search(r"Setup[- ]?Qualit[äa]t[:*\s]+\**\s*([^\n\.]{0,80})", content, re.IGNORECASE)
        prev_setup = m_setup.group(1).strip()[:80] if m_setup else "unknown"
        # Filename → Zeitstempel
        base = os.path.basename(prev).replace(".md","")
        # Delta
        delta_pct = ((current_price - prev_price)/prev_price*100) if (current_price and prev_price) else None
        # Zeit-Delta in Stunden
        try:
            prev_dt = datetime.strptime(base, "%Y-%m-%d_%Hh")
            age_h = (datetime.now() - prev_dt).total_seconds() / 3600
        except Exception:
            age_h = None
        return {
            "file": os.path.basename(prev),
            "timestamp": base,
            "age_h": age_h,
            "price": prev_price,
            "bias": prev_bias,
            "setup": prev_setup,
            "delta_pct": delta_pct,
            "current_price": current_price,
        }
    except Exception as e:
        return {"error": str(e)}


def format_previous_block(prev):
    if not prev or prev.get("error"):
        return "Keine vorherige Analyse verfügbar."
    parts = [
        f"Zeitpunkt: {prev['timestamp']} ({prev['age_h']:.1f}h alt)" if prev.get("age_h") is not None else f"Zeitpunkt: {prev['timestamp']}",
        f"Preis damals: ${prev['price']:,.0f}" if prev.get("price") else "Preis damals: n/a",
        f"Bias damals: {prev['bias']}",
        f"Setup damals: {prev['setup']}",
    ]
    if prev.get("delta_pct") is not None:
        arrow = "↑" if prev["delta_pct"] > 0 else "↓"
        parts.append(f"Preis-Delta seither: {arrow}{prev['delta_pct']:+.2f}% (jetzt ${prev['current_price']:,.0f})")
    return "\n".join(parts)


# ── Claude CLI Analyse ───────────────────────────────────────────────────────
def analyse_with_claude(summary_text, previous=None, track_summary=None):
    import subprocess, os

    prev_block = format_previous_block(previous)
    track_block = track_summary or "Track Record: keine Daten."

    prompt = f"""Du bist Trading-Sparring-Partner eines erfahrenen Traders (3 Jahre HL-Erfahrung). Ziel: **intraday-handelbare** Signale — nicht nur "Abwarten". Wenn kein Setup, dann konkreter Trigger für die nächsten Stunden.

═══════════════════════════════════════
TRACK RECORD (deine bisherigen Calls & Outcome)
═══════════════════════════════════════
{track_block}

═══════════════════════════════════════
VORHERIGE ANALYSE (Loop / Self-Review)
═══════════════════════════════════════
{prev_block}

═══════════════════════════════════════
AKTUELLE MARKTDATEN
═══════════════════════════════════════
{summary_text}

═══════════════════════════════════════
HARTE REGELN (aus 30-Tage-Backtest — nicht ignorieren)
═══════════════════════════════════════
**REGEL A — Kein reflex-Bearish:** Weekly-RSI <40 allein reicht NICHT für bearish-Bias. Bearish nur wenn ZUSÄTZLICH: (a) Daily schließt neues Low unter 20d-Range ODER (b) 1H bricht Struktur-Low mit >0.8% Impulskerze. Sonst → Neutral. Range-Markt (Daily oszilliert seit 5+ Tagen zwischen zwei EMAs) IMMER Neutral.

**REGEL B — Kein Short ohne Fuel:** Wenn `Kiy Liq Short >3× Long` UND `OI 48h` flach/negativ → Shorts sind ausgestoppt, kein Squeeze-Fuel. Short-Bias STREICHEN und aktiv nach Contrarian-Long-Wachsamkeit suchen.

**REGEL C — Zonen NUR aus Heatmap + Liq-Levels (keine %-Distanz-Regel):** Kritische Zonen MÜSSEN aus einer dieser Datenquellen im Summary stammen:
- **TBD Heatmap Top-Cluster** (1M, 7d, 3d, 1d) — je größer `size`, desto stärker
- **TBD Liq-Levels** über/unter Preis — bevorzuge `high`/`medium` Leverage-Cluster
- **Kiy Liq 48h**-Aggregat (Long/Short-Summen)

Confluence entsteht, wenn mehrere Timeframes (z.B. 1M + 7d oder 3d + Liq-Level) auf denselben Preis zeigen (±0.3% Toleranz zählen als selbe Zone). PDH/PDL/Weekly-Open/EMA/VWAP sind nur **sekundäre** Confluence, KEINE eigenständige Zone. Wähle Zonen, die für ein handelbares Setup Sinn ergeben — nahe Cluster für Entries, weiter entfernte für TP-Targets. Wenn keine relevanten Cluster verfügbar → Zone weglassen (kein Forced-Placement).

**REGEL D — Kein "Abwarten" ohne Trigger:** "Abwarten" ist NUR gültig mit expliziter Trigger-Formulierung: `Long ab $X (Bedingung: ...), Short ab $Y (Bedingung: ...)`. Wenn 1H-Range der letzten 8 Kerzen <0.8% ist → "Range-Breakout-Watch: Long >Range-High +0.3%, Short <Range-Low −0.3%".

**REGEL E — Contrarian-Filter:** Wenn (nach Regel A) noch bearish tendiert AND `Funding >0` AND `Perp-Discount (basis <0)` AND `CVD bullisch` AND `Short-Liq >> Long-Liq` → Bias auf **"Neutral, Contrarian-Long-Watch"** umbiegen. Diese Konfig hat historisch +0.57R Long-Payoff geliefert (vs. −0.44R Short).

**REGEL F — Bullish erlauben:** Bullish ist explizit gültig wenn: Daily-Preis >EMA50 UND 3× Higher-High-Sequenz auf Daily, ODER Weekly-RSI im Cross-through 45 nach oben. Wehr dich gegen reflexartige Bearish-Antworten wegen Weekly-Downtrend allein.

**REGEL G — Track-Record-Selbstkorrektur:** Der TRACK RECORD Block oben zeigt deine bisherige Bias-Hit-Rate und Warnungen bei Serien-Fehlern. Wenn dort Warnung "3 X-Calls in Folge daneben" steht → **diesen Bias JETZT nicht wiederholen**, auch wenn Daten dazu passen. Wenn Ø-Return bei einem Bias systematisch das falsche Vorzeichen hat → Bias-Schwelle härten oder Contrarian-Filter (Regel E) aktivieren.

**REGEL H — Anti-Rationalisierung bei Bias-Wiederholung:** Wenn Preis seit vorheriger Analyse >1% GEGEN den damaligen Bias gelaufen ist (z.B. vorheriger Long → Preis −1.2%), gilt:
- Loop-Check MUSS explizit mit "vorheriger [Bias] war falsch (Δ −X.X%)" beginnen. Formulierungen wie "war korrekt (kein Long-Call)" bei einem "Neutral, Contrarian-Long-Watch" sind **verboten** — Watch mit Long-Bias ZÄHLT als Long-Call für den Self-Check.
- Willst du denselben Bias wiederholen (z.B. wieder Long-Watch nach Long-Fehler), MUSS mind. **1 NEUER Datenpunkt** zitiert werden, der vorher nicht galt oder sich signifikant verschoben hat — konkret z.B.: "Retail L/S jetzt X% (vorher Y%)", "OI-Delta 10h gedreht auf +$XM (vorher −$YM)", "Bid/Ask-Delta jetzt +$XM (vorher −$YM)". Dieselben Regeln (B+E) mit den gleichen Zahlen zu wiederholen = Rationalisierung, verboten.
- Bei Ø-Return-Vorzeichen falsch UND Preis-Delta gegen alten Bias: Size-Factor **HALBIEREN** (max 0.5) ODER Setup als "SKIP — Bias-Failure-Cluster" markieren.

═══════════════════════════════════════
STRUKTUR DER ANTWORT (max 550 Wörter)
═══════════════════════════════════════
**🗣️ KLARTEXT (Pflicht, GANZ oben, 3–5 Zeilen, für den Trader-Kollegen am Handy):**
Sag in **Alltagssprache** was Sache ist und was zu tun ist. **KEIN Fachjargon.**
Verboten: LH/HL, HH/LL, CVD, EMA20/50/200, RSI-Zahlen, VWAP, Perp-Discount, Funding, OI, F&G, Sweep+Reclaim, BoS, ER, SAR, Compression, Confluence, R-Multiple.
Erlaubt sind Preise, Prozente, Uhrzeiten und Sätze wie: „Käufer/Verkäufer dominant", „steigende/fallende Tiefs", „Terminmarkt billiger als Kassa (Short-Nervosität)", „durchschnittlicher Tagespreis liegt bei $X als Magnet", „Preis klebt an gestrigem Hoch/Tief", „warte bis Preis über/unter $X mit klarer Kerze".
Struktur:
- 1 Satz **Lage** (bullish/bearish/seitwärts, wer dominiert)
- 1 Satz **Was tun** (traden ab $X, warten, nix machen — konkret)
- 1 Satz **Was killt die Idee** (bis wohin darf's laufen, dann bin ich falsch)

Danach folgt der Detail-Block für den Rest der Nachricht (den kannst du überfliegen).

──────────────

**0. Loop-Check — striktes Format (4 Zeilen, keine Prosa):**
- **Δ:** `Preis Δ_$XX (+/−Y.YY%) seit vorheriger Analyse` — und: `vorheriger Bias [Long/Short/Neutral/Long-Watch/Short-Watch] war [richtig/falsch]` (Watch mit Direction zählt als Direction-Call, siehe Regel H).
- **Track:** `Ø-Return für heutigen Bias-Kandidaten: X.XX% (n=Y)` — Vorzeichen [passt/passt-nicht]. Serien-Warnung [ja/nein].
- **Neuheit (nur nötig wenn du denselben Bias wie vorher willst):** Nenne den KONKRETEN neuen Datenpunkt der es diesmal rechtfertigt (Retail L/S / OI-Delta / Bid/Ask-Delta / Struktur-Change). Ohne Neuheit = Rationalisierung → Bias wechseln oder SKIP.
- **Size-Korrektur:** `full / half / skip` — begründet aus obigen 3 Zeilen (nach Regel H).

**1. HTF-Bias:** bullish/bearish/neutral — mit expliziter Regel-Referenz (welche der Regeln A/B/E/F angewendet wurde)

**1b. Order-Flow + Positioning (PFLICHT, aus TBD-Daten — jeder Datenpunkt einzeln zitiert):**
- **Retail L/S**: Zitiere aktuellen Long % und 10h-Trend. Interpretiere: >60% Long = Contrarian-Short-Warnung, <40% Long = Contrarian-Long-Confirmation, dazwischen = neutral. Trend-Änderung >5pp = Signal.
- **OI-Delta (10h Summe + aktuell)**: Zitiere beide Zahlen. Positiv = Fresh-Money Aufbau (Trend-Continuation-Hint), Negativ = Unwind (Ende Move / Capitulation). Vergleiche mit Preis-Delta: gleicher Vorzeichen = Trend-Bestätigung, gegenläufig = Divergenz.
- **Bid/Ask-Delta (10h Ø + aktuell)**: Zitiere beide. Konsistent negativ = Ask-Wall (Verkaufsdruck oben), konsistent positiv = Bid-Support (Käuferpolster unten). Drehung im 10h-Verlauf = Signal.
- **Confluence-Check:** Bestätigen die 3 Datenpunkte den HTF-Bias aus Punkt 1, oder widersprechen sie? Bei Widerspruch → HTF-Bias auf "Neutral" downgraden ODER Size halbieren.

**2. 1H-Struktur (Bias-Layer):** EMA-Stack, RSI, HH/HL vs LH/LL aus letzten 8 Kerzen, aktuelle Range-Breite. Definiert die **Richtung**.

**2b. 15M-Struktur (Entry-Timing-Layer — NEU, essenziell für Intraday):** EMA20/50/200-Stack + RSI + Struktur-Klassifikation (siehe "15M Struktur" im Summary). Prüfe:
   - **Divergenz zu 1H?** (z.B. 1H bearisch, 15m HH/HL → Bounce vor weiterem Down)
   - **Entry-Setup?** Klassische 15m-Trigger: EMA20-Reclaim/Rejection mit Volumen-Kerze, VWAP-Retest, RSI-Divergenz zu vorherigem Swing, Break of Micro-Structure (BoS)
   - **Range-Kompression?** (Range<0.5% über 8 Kerzen → Breakout-Trade vorbereiten)
   - **15m-Level-Referenz:** Wo liegen die 15m-Swing-Highs/Lows der letzten 8 Kerzen? Das sind die Intraday-Entry-Trigger.

**3. 4H-Rahmen:** ein Satz — passt zu 1H oder Divergenz

**4. Kritische Zonen (nur aus Heatmap 1M/7d/3d/1d + Liq-Levels — siehe Regel C):** je 2 oben/unten, Preis + Datenquelle (welches Cluster/welche Liq-Level, size) — nutze Cluster als Entry-Zonen (nah) und TP-Targets (weiter entfernt)

**5. INTRADAY-SETUP-CARD**

**SETUP-TYP-KATALOG — wähle den passenden Typ (nicht reflexartig Breakout!):**

| # | Typ | Wann anwendbar | Trigger-Beispiel |
|---|-----|----------------|-----------------|
| 1 | **Compression-Breakout** | 15m-Range <0.5% über 6+ Kerzen, Volumen sinkt, Preis nahe HTF-Level | 15m-Close über Range-High +0.15% Puffer mit Volumen-Spike |
| 2 | **Pullback-in-Trend (Continuation)** | 1H HH/HL klar, 15m Pullback zu EMA20/50 oder VWAP, RSI 15m 40-55 | Bull-Engulfing 15m an EMA20, RSI 15m dreht >50 |
| 3 | **Mean-Reversion / Range-Fade** | 1H seitwärts (Range >8h, klare Grenzen), kein HTF-Impuls, ATR normal | Preis touched Range-Kante, 15m Rejection-Kerze, Entry gegen Kante |
| 4 | **Liquidity-Sweep + Reclaim** (SMC) | Preis läuft kurz über/unter Swing-High/-Low (typ. PDH/PDL), sofort Reclaim, Kerze mit langem Docht | 15m Docht über PDH, Close zurück unter PDH → Short |
| 5 | **Failed Breakout (Reversal)** | Breakout-Kerze schließt über Level, nächste 1-2 Kerzen können nicht halten → Reclaim | 15m-Close zurück unter Break-Level → Gegen-Trade |
| 6 | **VWAP-Bounce / Rejection** | Preis touched Session-VWAP mit Reaktions-Kerze, Distanz zu VWAP >0.4% davor | Bull-Kerze an VWAP, SL knapp unter VWAP |
| 7 | **Momentum-Play nach News** | ≤30min nach High-Impact-Event, klare Impuls-Kerze, dann 1-2 Konsolidierungs-Kerzen | Break aus Konsolidierung in Impuls-Richtung |
| 8 | **RSI/CVD-Divergenz Reversal** | Preis macht neues Extrem (Local HH/LL), RSI 15m ODER CVD divergiert (macht kein neues Extrem) | Rejection-Kerze am Extrem, Entry mit Extrem als SL |

**Entscheidungslogik:**
- **Trend-Markt** (1H HH/HL oder LH/LL klar) → primär Typ **2** (Pullback), sekundär **4/5** (Sweep/Failed Break)
- **Range-Markt** (1H seitwärts, klare Grenzen) → primär Typ **3** (Range-Fade), sekundär **1** (Compression-Breakout) nur wenn Range extrem eng
- **Konsolidierung nach Impuls** → Typ **1** oder **7** (falls News)
- **Extrem-Zone erreicht** (PDH/PDL/HTF-Level nach längerem Impuls) → Typ **4/5/8** (Sweep/Failed/Divergenz)

**Pflicht:** Nenne den gewählten SETUP-TYP explizit und begründe warum genau dieser Typ zu den aktuellen Daten passt (Trend vs Range vs Impuls-Nachlauf, wo im Zyklus). Wenn 2 Setups plausibel, priorisiere Typ mit höherer Trefferquote in aktuellem Regime.

**Format der Card** — bindend. **Entry/SL basieren auf 15m-Swings (nicht 1H!)**, TPs auf 1H-Zonen/Reference-Levels.

**PFLICHT: R-Multiple sauber ausrechnen — Formel:**
- **Long:** `R = (TP − Entry) / (Entry − SL)` — Entry-Mitte der Zone, SL absoluter Preis
- **Short:** `R = (Entry − TP) / (SL − Entry)`
- **Zeige die Rechnung** hinter jedem TP als Kommentar in Klammern
- Beispiel Long: Entry $63,993, SL $63,617, TP2 $64,750 → R = (64,750−63,993)/(63,993−63,617) = 757/376 = **2.01R** ✓
- Beispiel Short: Entry $63,680, SL $64,030, TP2 $63,155 → R = (63,680−63,155)/(64,030−63,680) = 525/350 = **1.50R** ✓
- Falls TP <1R → TP verwerfen oder weiter setzen. Nur TPs mit R ≥1.0 akzeptabel.

```
SETUP-TYP: [Nummer + Name aus Katalog, z.B. "3 — Mean-Reversion / Range-Fade"]
BEGRÜNDUNG: [1 Satz warum dieser Typ zu aktueller Struktur passt]
BIAS: [Long/Short/Neutral-Watch]
TRIGGER: [Konkretes Preis-/Zeit-Ereignis — z.B. "15m-Close >$63,180 mit RSI>55" oder "VWAP-Reclaim + Bull-Engulfing 15m"]
ENTRY-ZONE: [Preisspanne aus 15m-Struktur, z.B. $63,180-$63,220 → Entry-Mitte $63,200]
STOP-LOSS: $XX,XXX  (15m-Swing-Low/High + Puffer, Risk = |Entry-SL| = $YY = Z.ZZ%)
TP1: $XX,XXX  (R = (TP1-Entry)/Risk = YY/YY = **N.NNR**)  [Confluence: PDH+Liq]
TP2: $XX,XXX  (R = (TP2-Entry)/Risk = YY/YY = **N.NNR**)  [Confluence: Heatmap+EMA]
TIME-STOP: [Wann ungültig — z.B. "wenn nicht bis 15:30 US-Open ausgelöst" oder "wenn 3× 15m-Kerzen ohne Trigger"]
INVALIDATION: [Killer — z.B. "15m-Close unter EMA50" oder "1H-Close < $62,900"]
```
Wenn Markt seitwärts UND keine klaren Range-Kanten: statt Card einen "WATCH-MODE" mit **2 Szenarien** (Long-Trigger UND Short-Trigger), jeweils mit Setup-Typ-Zuordnung — meist Typ 1 (Compression-Breakout) für Long, Typ 5 (Failed Breakout) für Short-Fake-Fänger. Auch dort R-Multiples ausrechnen.

**6. Offene HL-Positionen:** SL/TP-Anpassung sinnvoll? Konkret.

**7. Makro-Risiko-Fenster:** Nächstes High-Impact-Event mit Uhrzeit — davor keine Neu-Entries.

Direkt, konkret, keine Allgemeinplätze. Wenn Regeln A/B/E gegen "Bearish" sprechen → befolgen, auch wenn deine Intuition anders will."""

    try:
        node_bin = "/Users/Vuki/.nvm/versions/node/v18.20.8/bin"
        node_exe = f"{node_bin}/node"
        cli_js   = "/Users/Vuki/.nvm/versions/node/v18.20.8/lib/node_modules/@anthropic-ai/claude-code/cli.js"
        env = os.environ.copy()
        env["PATH"] = f"{node_bin}:{env.get('PATH', '/usr/bin:/bin')}"
        result = subprocess.run(
            [node_exe, cli_js, "--print", "--model", "claude-sonnet-4-6"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=360,
            env=env,
        )
        if result.returncode != 0:
            return f"[claude CLI Fehler: {result.stderr[:300]}]"
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        return "[Timeout bei Claude-Analyse]"
    except Exception as e:
        return f"[Fehler: {e}]"

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"[{time.strftime('%H:%M:%S')}] Trading-Analyse startet...")

    # Aktive Coins ermitteln: BTC immer + alle offenen HL-Positionen
    coins = ["BTC"]
    hl_check = post("https://api.hyperliquid.xyz/info", {"type": "clearinghouseState", "user": HL_WALLET})
    if isinstance(hl_check, dict) and "assetPositions" in hl_check:
        for p in hl_check["assetPositions"]:
            coin_p = p["position"].get("coin","")
            if coin_p and coin_p != "BTC" and float(p["position"].get("szi","0")) != 0:
                if coin_p not in coins:
                    coins.append(coin_p)
    print(f"  Coins: {coins}")

    # Daten holen
    print(f"[{time.strftime('%H:%M:%S')}] Hole Daten...")
    raw = fetch_all(coins)

    # Text-Summary
    summary = summarize(raw, coins)

    # Vorherige Analyse laden (Loop / Self-Review)
    try:
        current_price = float(raw.get("ohlcv_15m_BTC", [[0]*5])[-1][4])
    except Exception:
        current_price = None
    previous = load_previous_analysis(current_price=current_price)
    if previous and not previous.get("error"):
        print(f"  Vorherige: {previous.get('timestamp')} @ ${previous.get('price')} bias={previous.get('bias')} Δ={previous.get('delta_pct')}")

    # Track-Record: alte Calls anreichern, Summary für Prompt bauen
    track = load_track()
    if enrich_track(track):
        print(f"  Track-Record: alte Calls angereichert")
    track_summary = format_track_record(track, last_n=10)
    print(f"  Track-Record: {sum(1 for c in track.get('calls',[]) if c.get('outcome_evaluated_at'))} evaluierte / {len(track.get('calls',[]))} total Calls")

    # Claude-Analyse
    print(f"[{time.strftime('%H:%M:%S')}] Sende an Claude...")
    analysis = analyse_with_claude(summary, previous=previous, track_summary=track_summary)

    # Aktuellen Call in Track-Record eintragen (Outcome wird in nächstem Run ≥24h später ausgewertet)
    ts_key = time.strftime("%Y-%m-%d_%Hh")
    bias_new, setup_new = extract_bias_setup_from_analysis(analysis)
    if current_price:
        append_call(track, ts_key, current_price, bias_new, setup_new)
        save_track(track)
        print(f"  Track-Record: neuer Call gespeichert (bias={bias_new})")

    # Datei speichern
    ts = time.strftime("%Y-%m-%d_%Hh")
    fname = os.path.join(OUT_DIR, f"{ts}.md")
    with open(fname, "w") as f:
        f.write(f"# Trading Analyse — {time.strftime('%Y-%m-%d %H:%M UTC+2', time.localtime())}\n\n")
        f.write("## Rohdaten-Summary\n\n```\n")
        f.write(summary)
        f.write("\n```\n\n## Analyse\n\n")
        f.write(analysis)
    print(f"  Gespeichert: {fname}")

    # Telegram — Multi-Message-Split (limit 4096, mit HTML-Overhead ~3900 safe)
    clean = analysis.replace("**","").replace("##","").replace("---","—")
    clean = clean.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

    def split_msg(text, chunk_size=3800):
        """Splittet an Doppelnewline/Header-Grenzen, nie mitten im Wort."""
        chunks = []
        remaining = text
        while len(remaining) > chunk_size:
            cut = remaining.rfind("\n\n", 0, chunk_size)
            if cut < chunk_size // 2:
                cut = remaining.rfind("\n", 0, chunk_size)
            if cut < chunk_size // 2:
                cut = chunk_size
            chunks.append(remaining[:cut].rstrip())
            remaining = remaining[cut:].lstrip()
        if remaining:
            chunks.append(remaining)
        return chunks

    parts = split_msg(clean, chunk_size=3800)
    header_ts = time.strftime('%d.%m %H:%M', time.localtime())

    # Chart(s) VOR dem Text — 1h HTF-Kontext + 15m Setup-Detail
    setups = parse_setup_cards(analysis)
    zones = parse_critical_zones(analysis)
    print(f"  Setup-Cards geparst: {len(setups)}, kritische Zonen: {len(zones)}")
    for coin in coins:
        s_arg = setups if coin == "BTC" else None
        z_arg = zones  if coin == "BTC" else None

        # 1h HTF-Kontext (72h) — mit Vector-Kerzen + Zonen, ohne Setup
        png1h = render_chart_png(raw, coin=coin, n_candles=72, setups=None,
                                 interval="1h", zones=z_arg, mark_vectors=True)
        if png1h:
            ok = tg_photo(png1h, caption=f"📈 <b>{coin} · 1H · 72h HTF</b>  ·  Vector-Kerzen · krit. Zonen")
            print(f"  Chart {coin} 1h: {'OK' if ok else 'FEHLER'}")
            time.sleep(0.5)

        # 15m Setup-Detail (24h = 96 Kerzen) — Setup-Overlay + Swings + Vector + Zonen
        png15 = render_chart_png(raw, coin=coin, n_candles=96, setups=s_arg,
                                 interval="15m", zones=z_arg, mark_vectors=True)
        if png15:
            overlay = " · Setup + Swings + Vector" if s_arg else " · Swings + Vector"
            ok = tg_photo(png15, caption=f"🎯 <b>{coin} · 15m · 24h Setup</b>{overlay}")
            print(f"  Chart {coin} 15m: {'OK' if ok else 'FEHLER'}")
            time.sleep(0.5)

    for idx, part in enumerate(parts, 1):
        prefix = f"📊 <b>Pre-UK Analyse — {header_ts}</b>" if idx == 1 else f"📊 <b>...Fortsetzung ({idx}/{len(parts)})</b>"
        tg(f"{prefix}\n\n{part}")
        time.sleep(0.5)  # Rate-Limit-Schutz
    print(f"[{time.strftime('%H:%M:%S')}] Fertig ({len(parts)} Telegram-Msg).")

if __name__ == "__main__":
    main()
