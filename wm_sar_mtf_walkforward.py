#!/usr/bin/env python3
"""Walk-Forward des MTF-Level-Gates. Wie trenddir-walkforward, aber Kandidaten =
Level-Detektions-Params (rev%-Skala, Vektor-Schwelle). Frage: sagt IS-Ranking die
OOS-Performance vorher, oder sind die +171% overfit? Config: MTF+BCR, Einzelpos."""
import os, importlib, datetime as dt

DATA = "backtest/data/BTCUSDT_15m_4y.csv"
BND  = 1735689600  # 2025-01-01

# Kandidaten: variieren rev%-Skala (Strukturgranularitaet) + Vektor-Schwelle
CAND = [
    ("rev x0.6",       {'REV_MULT':'0.6','LV_VEC_MULT':'1.5'}),
    ("rev x0.8",       {'REV_MULT':'0.8','LV_VEC_MULT':'1.5'}),
    ("rev x1.0",       {'REV_MULT':'1.0','LV_VEC_MULT':'1.5'}),
    ("rev x1.3",       {'REV_MULT':'1.3','LV_VEC_MULT':'1.5'}),
    ("rev x1.6",       {'REV_MULT':'1.6','LV_VEC_MULT':'1.5'}),
    ("rev1.0 vec1.3",  {'REV_MULT':'1.0','LV_VEC_MULT':'1.3'}),
    ("rev1.0 vec2.0",  {'REV_MULT':'1.0','LV_VEC_MULT':'2.0'}),
]

def metrics(tr, seq):
    if not tr: return dict(n=0, ret=0.0, pf=float('nan'), dd=0.0)
    gp=sum(t.r for t in tr if t.r>0); gl=-sum(t.r for t in tr if t.r<=0)
    pf=gp/gl if gl>0 else float('inf')
    end=tr[-1].equity_after; peak=seq; dd=0.0
    for t in tr:
        peak=max(peak,t.equity_after); dd=max(dd,(peak-t.equity_after)/peak)
    return dict(n=len(tr), ret=end/seq-1, pf=pf, dd=dd)

def yearly(tr):
    y={}
    for t in tr: y[dt.datetime.utcfromtimestamp(t.exit_t).year]=y.get(dt.datetime.utcfromtimestamp(t.exit_t).year,0.0)+t.r
    return y

def run_one(env):
    base={'MW_ON':'1','BCR_ON':'1','BCR_FLAT':'1','CTE_ON':'0','E200_ON':'0','SLOPE_ON':'0',
          'HTF_ON':'0','REGIME_ON':'0','NOPYR':'1','RO_ON':'0','TDIR_ON':'0','MTF_ON':'1',
          'MTF_MACRO':'1','MTF_RBTOL':'0.005','VEC_MULT':'99.0'}
    base.update(env); os.environ.update(base)
    import levels_mtf as L; importlib.reload(L)         # REV/VEC neu aus env
    import wm_sar_mtf as m; importlib.reload(m)          # MTF-Flags neu
    bars=m.load_csv(DATA)
    tr,eq,dd,mc=m.run(bars)
    is_t=[t for t in tr if t.exit_t<BND]; oos=[t for t in tr if t.exit_t>=BND]
    return (metrics(is_t,m.INIT_CAP),
            metrics(oos, is_t[-1].equity_after if is_t else m.INIT_CAP),
            metrics(tr,m.INIT_CAP), yearly(tr), dd)

def fmt(m):
    if m['n']==0: return f"{'—':>7} {'—':>5} {'—':>5} {0:>4}"
    pf='inf' if m['pf']==float('inf') else f"{m['pf']:.2f}"
    return f"{m['ret']*100:+6.0f}% {pf:>5} {m['dd']*100:4.0f}% {m['n']:>4}"

def main():
    print(f"MTF Walk-Forward  IS<2025-01-01<OOS\n")
    hdr=f"{'Kandidat':<15} | {'IS ret':>7} {'PF':>5} {'DD':>5} {'N':>4} | {'OOS ret':>7} {'PF':>5} {'DD':>5} {'N':>4} | {'Full':>6} {'2023R':>6}"
    print(hdr); print('-'*len(hdr))
    rows=[]
    for label,env in CAND:
        ism,oosm,full,yr,bardd=run_one(env)
        rows.append((label,ism,oosm,full,yr))
        print(f"{label:<15} | {fmt(ism)} | {fmt(oosm)} | {full['ret']*100:+5.0f}% {yr.get(2023,0):+5.0f}")
    # Spearman IS-ret vs OOS-ret
    isr=[r[1]['ret'] for r in rows]; oosr=[r[2]['ret'] for r in rows]
    def ranks(v):
        o=sorted(range(len(v)),key=lambda i:v[i]); r=[0]*len(v)
        for p,i in enumerate(o): r[i]=p
        return r
    ri,ro=ranks(isr),ranks(oosr); nn=len(rows)
    rho=1-6*sum((ri[i]-ro[i])**2 for i in range(nn))/(nn*(nn**2-1))
    print(f"\nSpearman rho(IS-ret, OOS-ret) = {rho:+.3f}  (n={nn})")
    bi=max(range(nn),key=lambda i:isr[i]); bo=max(range(nn),key=lambda i:oosr[i])
    print(f"Bestes IS:  {rows[bi][0]}  -> OOS-Rang {nn-ro[bi]}/{nn}, OOS {oosr[bi]*100:+.0f}%")
    print(f"Bestes OOS: {rows[bo][0]}  (IS {isr[bo]*100:+.0f}%)")
    pos=sum(1 for r in oosr if r>0)
    print(f"OOS positiv: {pos}/{nn} Kandidaten")

if __name__=="__main__":
    main()
