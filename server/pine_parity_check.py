#!/usr/bin/env python3
"""
Pine↔Python-Paritätsprüfung für einen konkreten Zeitpunkt.

Beantwortet bei "TV zeigt Marker X, Journal zeigt nichts" deterministisch:
  - Was sagt die Engine an dem Bar (Roh-Signal? Gate-Grund? Kontextwerte)?
  - Was hätte Pine-v22 (ALTE Semantik: laufender HTF-Bar) beim ER-Gate entschieden?
  - Was sagt Pine-v23 (= Python-Semantik)?
Wenn beide Semantiken das Signal blocken, liegt es NICHT an der HTF-Semantik
-> Chart-Symbol (Spot vs Perp!) oder Pine-Version im Chart prüfen.

Nutzung:
  python3 server/pine_parity_check.py 2026-08-18T10:00      # UTC+2
  python3 server/pine_parity_check.py 2026-08-18T10:00 --window 4
"""
import os, sys, argparse, bisect, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

from signal_watcher import CHAMP  # noqa: E402
for k, v in CHAMP.items():
    os.environ.setdefault(k, v)

import wm_sar_mtf as ENGINE   # noqa: E402
import levels_mtf as LV       # noqa: E402

U2 = lambda t: dt.datetime.utcfromtimestamp(t + 7200).strftime('%d.%m %H:%M')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('when', help='YYYY-MM-DDTHH:MM in UTC+2')
    ap.add_argument('--window', type=float, default=2.0, help='Stunden +/- (default 2)')
    ap.add_argument('--csv', default=os.path.join(os.environ.get('SERVER_DIR', HERE),
                                                  'data', 'BTCUSDT_15m_live.csv'))
    a = ap.parse_args()
    target = int(dt.datetime.fromisoformat(a.when)
                 .replace(tzinfo=dt.timezone.utc).timestamp()) - 7200
    win = int(a.window * 3600)

    bars = ENGINE.load_csv(a.csv)
    ENGINE.run(bars)
    print(f"CSV: {len(bars)} Bars bis {U2(bars[-1].t)} UTC+2\n")

    print(f"=== Engine-Signale {U2(target-win)} .. {U2(target+win)} ===")
    hits = [s for s in ENGINE.LAST_SIGNALS if target - win <= s['t'] <= target + win]
    if not hits:
        print("  KEIN Roh-Signal in diesem Fenster.")
        print("  -> Pine sieht etwas, das Pythons Detektor nicht sieht:")
        print("     Chart-Symbol (BINANCE:BTCUSDT.P vs Spot!) und Pine-Version prüfen.")
    for s in hits:
        print(f"  {U2(s['t'])} {s['tag']}/{s.get('side','?')} dir={s['dir']:+d} "
              f"@{s['px']:.1f} -> gate={s['gate']}")
        print(f"      bias4={s.get('bias4')} l1={s.get('l1')} l4={s.get('l4')} "
              f"d1={s.get('d1')} er={s.get('er')}")

    # ER unter beiden Semantiken
    N = int(os.environ.get('ER_N', '30')); ERMIN = float(os.environ.get('ER_MIN', '0.20'))
    hb, ct = LV.resample(bars, 14400)
    closes = [b.c for b in hb]
    er_closed = LV.efficiency_ratio(closes, N)

    def er_dev(prev, cur):
        seq = (prev + [cur])[-(N + 1):]
        if len(seq) < N + 1:
            return 0.0
        net = abs(seq[-1] - seq[0])
        vol = sum(abs(seq[k] - seq[k - 1]) for k in range(1, len(seq)))
        return net / vol if vol else 0.0

    print(f"\n=== ER-Gate (Schwelle {ERMIN}) — v23/Python vs v22-alt ===")
    diff_found = False
    for b in bars:
        if not (target - win <= b.t <= target + win):
            continue
        j = bisect.bisect_right(ct, b.t) - 1
        py, dev = er_closed[j], er_dev(closes[:j + 1], b.c)
        d = (py >= ERMIN) != (dev >= ERMIN)
        diff_found |= d
        mark = '  <-- SEMANTIK-DIVERGENZ' if d else ''
        star = ' *SIGNAL*' if any(s['t'] == b.t for s in hits) else ''
        print(f"  {U2(b.t)}  v23/Python {py:.3f} {'OFFEN' if py>=ERMIN else 'ZU   '} | "
              f"v22-alt {dev:.3f} {'OFFEN' if dev>=ERMIN else 'ZU   '}{mark}{star}")

    print("\n=== Befund ===")
    if hits and not diff_found:
        print("  Roh-Signal vorhanden, aber BEIDE Semantiken blocken identisch.")
        print("  -> Die HTF-Semantik erklärt einen TV-Marker hier NICHT.")
        print("  -> Nächste Verdächtige, in dieser Reihenfolge:")
        print("     1. Chart-Symbol: BINANCE:BTCUSDT.P (Perp) — NICHT Spot BTCUSDT!")
        print("     2. Pine-Version im Chart: 'TBD W/M SAR v23 Champion' (Slot-Version >= 86)")
        print("     3. Inputs im Settings-Panel vs active_config.json")
        print("     4. Offene (unbestätigte) Kerze auf dem Chart")
    elif diff_found:
        print("  Semantik-Divergenz im Fenster: ein v22-Chart konnte hier abweichen.")
        print("  Mit v23 ist das behoben — Chart auf v23 aktualisieren.")


if __name__ == '__main__':
    main()
