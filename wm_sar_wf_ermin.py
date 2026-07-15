#!/usr/bin/env python3
"""Walk-Forward ER_MIN (4h-Raster, v21-Basis).
Modus 1: --run 0.12,0.14  -> Engine je ER_MIN laufen lassen, Trades nach /tmp/wf_cache/*.json
Modus 2: --analyze        -> Segmente auswerten (expanding IS -> naechstes Halbjahr OOS)
"""
import os, sys, json, argparse, importlib, datetime as dt

CACHE = '/tmp/wf_cache'
DATA = "backtest/data/BTCUSDT_15m_4y.csv"
BASE = {'MW_ON':'1','BCR_ON':'1','BCR_FLAT':'1','CTE_ON':'0','E200_ON':'0','SLOPE_ON':'0',
        'HTF_ON':'0','REGIME_ON':'0','NOPYR':'1','RO_ON':'0','TDIR_ON':'0','MTF_ON':'1',
        'BIAS_MODE':'h4','MTF_MACRO':'1','MTF_RBTOL':'0.005',
        'REV_1D':'0.066','REV_4H':'0.033','REV_1H':'0.0165',
        'ER_N':'30','ER_TF':'4h','VEC_MULT':'99','LV_VEC_MULT':'1.5',
        'RISK':'0.01','MAX_LEV':'10','VT_ON':'0','CC_BIAS':'0','BCR_WT_ONLY':'1'}

# OOS-Segmente (Halbjahre), IS = alles davor (expanding)
SEGS = [("H2-2024", "2024-07-01", "2025-01-01"),
        ("H1-2025", "2025-01-01", "2025-07-01"),
        ("H2-2025", "2025-07-01", "2026-01-01"),
        ("H1-2026", "2026-01-01", "2026-12-31")]
TS = lambda s: int(dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc).timestamp())


def run_candidates(erlist):
    os.makedirs(CACHE, exist_ok=True)
    for er in erlist:
        os.environ.update(BASE); os.environ['ER_MIN'] = f"{er:.2f}"
        import wm_sar_mtf as m; importlib.reload(m)
        bars = m.load_csv(DATA)
        tr, eq, dd, mc = m.run(bars)
        out = [dict(entry_t=t.entry_t, exit_t=t.exit_t, r=t.r) for t in tr]
        json.dump(out, open(f"{CACHE}/er{er:.2f}.json", 'w'))
        print(f"ER_MIN {er:.2f}: N {len(tr)}  sumR {sum(t.r for t in tr):+.1f}  cached")


def analyze():
    import glob
    cands = {}
    for f in sorted(glob.glob(f"{CACHE}/er*.json")):
        er = float(os.path.basename(f)[2:6])
        cands[er] = json.load(open(f))
    ers = sorted(cands)
    print("Kandidaten:", " ".join(f"{e:.2f}" for e in ers))

    def sumr(er, t0, t1):
        return sum(t['r'] for t in cands[er] if t0 <= t['entry_t'] < t1), \
               sum(1 for t in cands[er] if t0 <= t['entry_t'] < t1)

    t_start = min(t['entry_t'] for t in cands[ers[0]])
    stitched_wf = 0.0; stitched_fix = 0.0
    picks = []
    print(f"\n{'Segment':9s} {'IS-Wahl':7s} | OOS-R je Kandidat " +
          " ".join(f"{e:.2f}" for e in ers))
    for name, s0, s1 in SEGS:
        t0, t1 = TS(s0), TS(s1)
        is_scores = {er: sumr(er, t_start, t0)[0] for er in ers}
        pick = max(is_scores, key=is_scores.get)
        oos = {er: sumr(er, t0, t1) for er in ers}
        stitched_wf += oos[pick][0]
        stitched_fix += oos[0.20][0]
        picks.append(pick)
        row = " ".join(f"{oos[er][0]:+5.1f}" for er in ers)
        print(f"{name:9s}  {pick:.2f}   | {row}   (N pick: {oos[pick][1]})")
    print(f"\nGewählte ER_MIN je Schritt: {['%.2f'%p for p in picks]}")
    print(f"Stitched OOS-R  Walk-Forward: {stitched_wf:+.1f}")
    print(f"Stitched OOS-R  fix 0.20    : {stitched_fix:+.1f}")
    # Rangkorrelation IS-Wahl vs OOS je Segment
    try:
        def rho(xs, ys):
            n = len(xs)
            rk = lambda v: {x: i for i, x in enumerate(sorted(range(n), key=lambda k: v[k]))}
            import statistics
            rx = [sorted(range(n), key=lambda k: xs[k]).index(i) for i in range(n)]
            ry = [sorted(range(n), key=lambda k: ys[k]).index(i) for i in range(n)]
            mx, my = sum(rx)/n, sum(ry)/n
            num = sum((rx[i]-mx)*(ry[i]-my) for i in range(n))
            den = (sum((rx[i]-mx)**2 for i in range(n)) * sum((ry[i]-my)**2 for i in range(n)))**0.5
            return num/den if den else 0.0
        print("\nSpearman rho(IS-sumR, OOS-sumR) je Segment:")
        for name, s0, s1 in SEGS:
            t0, t1 = TS(s0), TS(s1)
            xs = [sumr(er, t_start, t0)[0] for er in ers]
            ys = [sumr(er, t0, t1)[0] for er in ers]
            print(f"  {name}: {rho(xs, ys):+.2f}")
    except Exception as e:
        print("rho-Fehler:", e)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', default='')
    ap.add_argument('--analyze', action='store_true')
    a = ap.parse_args()
    if a.run:
        run_candidates([float(x) for x in a.run.split(',')])
    if a.analyze:
        analyze()
