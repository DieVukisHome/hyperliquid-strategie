#!/usr/bin/env python3
"""Vergleicht MTF-Level-Gate vs EMA-slope-Baseline ueber 4 Jahre.
Zeigt Jahres-R (2023-Frage!), Gesamt-Return/PF/DD und IS/OOS-Split."""
import os, importlib, datetime as dt

DATA = "backtest/data/BTCUSDT_15m_4y.csv"
BND  = 1735689600  # 2025-01-01

def yearly_R(trades):
    yr = {}
    for t in trades:
        y = dt.datetime.utcfromtimestamp(t.exit_t).year
        yr[y] = yr.get(y, 0.0) + t.r
    return yr

def metrics(trades, start_eq):
    if not trades: return dict(n=0, ret=0, pf=float('nan'), dd=0)
    sr = sum(t.r for t in trades)
    gp = sum(t.r for t in trades if t.r > 0); gl = -sum(t.r for t in trades if t.r <= 0)
    pf = gp/gl if gl > 0 else float('inf')
    end = trades[-1].equity_after
    peak = start_eq; dd = 0
    for t in trades:
        peak = max(peak, t.equity_after); dd = max(dd, (peak-t.equity_after)/peak)
    return dict(n=len(trades), ret=end/start_eq-1, pf=pf, dd=dd, sumr=sr)

def run_cfg(label, env):
    base = {'MW_ON':'1','BCR_ON':'0','CTE_ON':'0','E200_ON':'0','SLOPE_ON':'0',
            'HTF_ON':'0','REGIME_ON':'0','NOPYR':'1','RO_ON':'0','TDIR_ON':'0','MTF_ON':'0'}
    base.update(env); os.environ.update(base)
    import wm_sar_mtf as m; importlib.reload(m)
    bars = m.load_csv(DATA)
    tr, eq, dd, mc = m.run(bars)
    full = metrics(tr, m.INIT_CAP)
    is_t = [t for t in tr if t.exit_t < BND]; oos = [t for t in tr if t.exit_t >= BND]
    is_m = metrics(is_t, m.INIT_CAP)
    oos_m = metrics(oos, is_t[-1].equity_after if is_t else m.INIT_CAP)
    yr = yearly_R(tr)
    print(f"\n### {label}")
    print(f"  Full: {full['ret']*100:+.0f}%  PF {full['pf']:.2f}  DD {full['dd']*100:.0f}%  N {full['n']}  (barDD {dd*100:.0f}%)")
    print(f"  IS  : {is_m['ret']*100:+.0f}%  PF {is_m['pf']:.2f}  DD {is_m['dd']*100:.0f}%  N {is_m['n']}")
    print(f"  OOS : {oos_m['ret']*100:+.0f}%  PF {oos_m['pf']:.2f}  DD {oos_m['dd']*100:.0f}%  N {oos_m['n']}")
    print(f"  Jahres-R: " + "  ".join(f"{y}:{yr[y]:+.0f}" for y in sorted(yr)))
    return full, yr

if __name__ == "__main__":
    print("="*70)
    run_cfg("BASELINE EMA-slope N1440 (TDIR)", {'TDIR_ON':'1','TDIR_MODE':'slope','TDIR_N':'1440','TDIR_TH':'0.0'})
    run_cfg("MTF Level-Gate (MW-only)", {'MTF_ON':'1'})
    run_cfg("MTF Level-Gate + BCR-Entries", {'MTF_ON':'1','BCR_ON':'1','BCR_FLAT':'1'})
    print("\n" + "="*70)
