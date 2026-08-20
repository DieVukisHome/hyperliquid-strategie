#!/usr/bin/env python3
"""
cycle_v2 — TBD-Zyklus-Buchführung (Stufe 0 des HTF-Umbaus).

EIGENSTÄNDIG, ändert nichts am Champion.

ARCHITEKTUR (Wookie, 20.8.):
  * Gezählt wird NUR auf der kleinsten Ebene (15m). Höhere Ebenen sind
    AGGREGATION: 3 × 15m-Stufe = 1 × 1h-Stufe = 1/3 × 4h-Stufe.
  * Das Stufenende wird RETROSPEKTIV datiert: die Stufe endet am Extrem des
    Beins, sobald der Retrace (Board Meeting) einsetzt. Lag ist unkritisch,
    weil am Stufenende ohnehin kein Entry sitzt (Entry = BCR/M-W-P3).
  * Die signifikante Kerze (SVC/Ablehnung) sitzt auf der Ebene, die den Zyklus
    ABSCHLIESST — auf 15m darf das Extrem unsauber aussehen. Deshalb ist die
    Kerzenform hier nur Diagnose, nicht Trigger.

Nutzung:
    python3 cycle_v2.py --selftest
"""
import os, sys, argparse, datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wm_sar_mtf as M
import levels_mtf as LV

U = lambda t: dt.datetime.utcfromtimestamp(t + 7200).strftime('%d.%m %H:%M')
T = lambda s: int(dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc).timestamp()) - 7200
TF = {'15m': 900, '1h': 3600, '4h': 14400}

FIB_MIN = float(os.environ.get('FIB_MIN', '0.382'))    # Board Meeting = echter Retrace
TOL_50  = float(os.environ.get('TOL_50', '0.0015'))    # 50er-Retest-Toleranz
FLAT_N  = int(os.environ.get('FLAT_N', '4'))           # ab Stufe 2: Board Meeting darf FLACH sein


def prep(bars, sec):
    hb, _ = LV.resample(bars, sec)
    c = [x.c for x in hb]
    return hb, M.ema_series(c, 50), M.ema_series(c, 200), \
        [sum(x.v for x in hb[max(0, j-10):j]) / max(1, len(hb[max(0, j-10):j])) for j in range(len(hb))]


def form(b, d):
    """Diagnose der Kerze am Extrem: Docht gegen Laufrichtung, Body."""
    rng = b.h - b.l
    if rng <= 0:
        return 0.0, 0.0
    wick = (min(b.o, b.c) - b.l) / rng if d < 0 else (b.h - max(b.o, b.c)) / rng
    return wick, abs(b.c - b.o) / rng


HOEHER = {'15m': '1h', '1h': '4h', '4h': None}
WICK_MIN = float(os.environ.get('WICK_MIN', '0.50'))


def zaehle_15m(bars, start_ts, d, ende_ts=None, p1_eltern=None, tf='15m'):
    """Retrospektive Stufenzählung. Stufe endet am Extrem, bestätigt durch den Retrace."""
    hb, e50, e200, vs = prep(bars, TF[tf])
    ho = HOEHER[tf]
    if ho:
        hb2, _, _, vs2 = prep(bars, TF[ho])
        sec2 = TF[ho]
        idx2 = {x.t: j for j, x in enumerate(hb2)}
    def docht_ok(j):
        """Ablehnung auf der EIGENEN Ebene ODER auf der naechsthoeheren
        (die signifikante Kerze sitzt auf der Ebene, die den Zyklus abschliesst)."""
        w, _ = form(hb[j], d)
        if w >= WICK_MIN:
            return True, w, 'eigen'
        if ho:
            t2 = (hb[j].t // sec2) * sec2
            if t2 in idx2:
                w2, _ = form(hb2[idx2[t2]], d)
                if w2 >= WICK_MIN:
                    return True, w2, ho
        return False, w, '-'
    out, stufe, phase = [], 0, 'IMPULS'
    ziel_erreicht = False          # Stufe 1: 200er muss erreicht sein
    extrem = extrem_t = extrem_j = None
    bein_start = None
    letztes_extrem = None
    vol_seg = 0.0

    for j, b in enumerate(hb):
        if b.t < start_ts or (ende_ts and b.t > ende_ts):
            if ende_ts and b.t > ende_ts:
                break
            continue
        if p1_eltern is not None and ((d < 0 and b.c > p1_eltern) or (d > 0 and b.c < p1_eltern)):
            out.append(dict(art='INVALIDIERT', t=b.t, px=b.c)); break

        if phase == 'IMPULS':
            if extrem is None:
                bein_start = b.h if d < 0 else b.l
            if extrem is None or (d < 0 and b.l < extrem) or (d > 0 and b.h > extrem):
                extrem, extrem_t, extrem_j = (b.l if d < 0 else b.h), b.t, j
                vol_seg = 0.0
            vol_seg += b.v
            # Stufe 1 endet NUR nach Lauf zur 200er (wenn sie in Laufrichtung liegt)
            if stufe == 0:
                e200_voraus = (d < 0 and e200[j] < bein_start) or (d > 0 and e200[j] > bein_start)
                if not e200_voraus:
                    ziel_erreicht = True          # 200er hinter dem Preis -> keine Bedingung
                elif (d < 0 and b.l <= e200[j]) or (d > 0 and b.h >= e200[j]):
                    ziel_erreicht = True
            # Board Meeting erkannt -> Stufe endete RÜCKWIRKEND am Extrem
            rueck = abs((b.h if d < 0 else b.l) - extrem)
            spanne = abs(bein_start - extrem)
            an_50 = (d < 0 and b.h >= e50[j] * (1 - TOL_50)) or (d > 0 and b.l <= e50[j] * (1 + TOL_50))
            fib_ok = spanne > 0 and rueck >= FIB_MIN * spanne
            ok_d, w_used, wo = (docht_ok(extrem_j) if extrem_j is not None else (False, 0, '-'))
            # Stufe 1: Lauf zur 200er + echter Retrace (50er + Fib).
            # Ab Stufe 2: Board Meeting darf FLACH sein -> Pause ohne neues Extrem genuegt.
            if stufe == 0:
                board = an_50 and fib_ok and ziel_erreicht
            else:
                flach = (j - extrem_j) >= FLAT_N
                board = fib_ok or flach
            if board and extrem_t != b.t and ok_d:
                stufe += 1
                w, bd = form(hb[extrem_j], d)
                vx = hb[extrem_j].v / vs[extrem_j] if vs[extrem_j] else 0
                out.append(dict(art=f'STUFE {stufe}', t=extrem_t, px=extrem,
                                docht=round(w_used * 100), wo=wo, body=round(bd * 100), vol=round(vx, 2),
                                bestaetigt=b.t, vol_seg=round(vol_seg)))
                letztes_extrem = extrem
                extrem = extrem_t = None
                ziel_erreicht = False
                phase = 'WARTE_BREAK'
        elif phase == 'WARTE_BREAK':
            if (d < 0 and b.l < letztes_extrem) or (d > 0 and b.h > letztes_extrem):
                phase = 'IMPULS'
                bein_start = letztes_extrem
                extrem, extrem_t, extrem_j = (b.l if d < 0 else b.h), b.t, j
                vol_seg = b.v
    return out


FAELLE = [
    dict(name='Fall D/E  15m abwärts (→ 1h-Stufe 1 = 3. Stufe)', tf='15m',
         start='2026-05-11T20:00', d=-1, ende='2026-05-13T00:00',
         soll=[('15m-Stufe 1', 80661), ('15m-Stufe 2', 80444), ('15m-Stufe 3 = 1h-St.1', 79801)]),
    dict(name='Fall A  15m abwärts', tf='15m', start='2026-08-10T10:00', d=-1,
         ende='2026-08-14T20:00', soll=[('15m-Stufe 1', 63788), ('15m-Stufe 2', 63222), ('15m-Stufe 3', 62484)]),
    dict(name='Fall C  1h abwärts (Kontrolle auf 1h)', tf='1h', start='2026-05-06T13:00', d=-1,
         ende='2026-05-08T12:00', soll=[('Stufe 1', 79462), ('Stufe 2', 79137)]),
    dict(name='Fall C  1h aufwärts (Kontrolle auf 1h)', tf='1h', start='2026-05-08T15:00', d=+1,
         ende='2026-05-11T06:00', soll=[('Stufe 1', 80642), ('Stufe 2', 81043), ('Stufe 3', 82460)]),
]


def selftest(csv):
    bars = M.load_csv(csv)
    ok = ges = 0
    for f in FAELLE:
        res = zaehle_15m(bars, T(f['start']), f['d'], T(f['ende']), tf=f['tf'])
        st = [r for r in res if r['art'].startswith('STUFE')]
        print(f"\n### {f['name']}")
        for r in st[:6]:
            print(f"   {r['art']}  {U(r['t'])}  {r['px']:9,.0f}   "
                  f"[Docht {r['docht']}% ({r['wo']}) Vol {r['vol']}x, best. {U(r['bestaetigt'])}]")
        print("   → Abgleich:")
        for i, (lab, soll) in enumerate(f['soll']):
            ges += 1
            if i < len(st):
                ist = st[i]['px']; ab = (ist / soll - 1) * 100
                t = abs(ab) <= 0.15; ok += t
                print(f"      {lab}: Soll {soll:,} · Ist {ist:,.0f} · {ab:+.2f}%  {'TREFFER' if t else 'daneben'}")
            else:
                print(f"      {lab}: Soll {soll:,} · Ist —  FEHLT")
    print(f"\n=== {ok}/{ges} Stufen getroffen (Toleranz 0,15%) ===")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--csv', default='backtest/data/BTCUSDT_15m_4y.csv')
    a = ap.parse_args()
    if a.selftest:
        selftest(a.csv)
