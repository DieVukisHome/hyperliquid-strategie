#!/usr/bin/env python3
"""
Binance Futures Klines Fetcher (public API, kein Key noetig)

Holt USDT-M Perpetual Kerzen via https://fapi.binance.com/fapi/v1/klines
und speichert sie als CSV (time_utc, open, high, low, close, volume).

Beispiele:
    python3 fetch_binance_data.py                          # BTCUSDT 5m, letzte 90 Tage
    python3 fetch_binance_data.py --symbol ETHUSDT --days 30
    python3 fetch_binance_data.py --interval 15m --start 2026-05-01 --end 2026-06-11

Nur Standardbibliothek, keine Installation noetig.
"""
import argparse
import csv
import json
import ssl
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

API = "https://fapi.binance.com/fapi/v1/klines"
LIMIT = 1500  # max Kerzen pro Request


def make_ssl_context():
    """macOS-Fix: python.org-Installationen haben oft keine System-Zertifikate.
    Reihenfolge: certifi (falls installiert) -> Standard -> unverifiziert (Warnung)."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    ctx = ssl.create_default_context()
    try:
        urllib.request.urlopen("https://fapi.binance.com/fapi/v1/ping",
                               timeout=10, context=ctx)
        return ctx
    except ssl.SSLError:
        print("WARNUNG: Zertifikatspruefung fehlgeschlagen — fahre unverifiziert fort.\n"
              "Dauerhafte Loesung: '/Applications/Python 3.12/Install Certificates.command'"
              " ausfuehren oder 'pip3 install certifi'.", file=sys.stderr)
        return ssl._create_unverified_context()
    except Exception:
        return ctx


SSL_CTX = make_ssl_context()


def fetch_chunk(symbol: str, interval: str, start_ms: int, end_ms: int):
    url = (f"{API}?symbol={symbol}&interval={interval}"
           f"&startTime={start_ms}&endTime={end_ms}&limit={LIMIT}")
    req = urllib.request.Request(url, headers={"User-Agent": "tbd-backtest/1.0"})
    with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as r:
        return json.loads(r.read())


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="BTCUSDT")
    p.add_argument("--interval", default="5m")
    p.add_argument("--days", type=int, default=90, help="Zeitraum rueckwirkend ab jetzt")
    p.add_argument("--start", help="UTC, z.B. 2026-05-01 (ueberschreibt --days)")
    p.add_argument("--end", help="UTC, z.B. 2026-06-11 (default: jetzt)")
    p.add_argument("--out", help="Ziel-CSV (default: data/<symbol>_<interval>.csv)")
    a = p.parse_args()

    end = (datetime.strptime(a.end, "%Y-%m-%d").replace(tzinfo=timezone.utc)
           if a.end else datetime.now(timezone.utc))
    start = (datetime.strptime(a.start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
             if a.start else end - timedelta(days=a.days))

    out = Path(a.out) if a.out else Path(__file__).parent / "data" / f"{a.symbol}_{a.interval}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)

    start_ms, end_ms = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
    rows, cursor = [], start_ms
    print(f"Lade {a.symbol} {a.interval}  {start:%Y-%m-%d} -> {end:%Y-%m-%d %H:%M} UTC")

    while cursor < end_ms:
        try:
            chunk = fetch_chunk(a.symbol, a.interval, cursor, end_ms)
        except Exception as e:
            print(f"  Fehler: {e} — warte 5s, versuche erneut", file=sys.stderr)
            time.sleep(5)
            continue
        if not chunk:
            break
        for k in chunk:
            # k: [openTime, open, high, low, close, volume, closeTime, ...]
            rows.append([k[0] // 1000, k[1], k[2], k[3], k[4], k[5]])
        cursor = chunk[-1][0] + 1
        done = datetime.fromtimestamp(rows[-1][0], tz=timezone.utc)
        print(f"  {len(rows):>7} Kerzen ... bis {done:%Y-%m-%d %H:%M}", end="\r")
        time.sleep(0.25)  # API schonen (Rate Limit 2400 weight/min)

    # Duplikate raus, sortieren
    seen, clean = set(), []
    for r in rows:
        if r[0] not in seen:
            seen.add(r[0])
            clean.append(r)
    clean.sort(key=lambda r: r[0])

    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time", "open", "high", "low", "close", "volume"])
        w.writerows(clean)

    print(f"\nFertig: {len(clean)} Kerzen -> {out}")


if __name__ == "__main__":
    main()
