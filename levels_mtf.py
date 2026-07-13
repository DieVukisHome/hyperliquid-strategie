#!/usr/bin/env python3
"""
Multi-TF Level-State Engine (TBD) — Schritt 1: DETEKTION + DIAGNOSE.

Liefert pro 15m-Bar (kausal, kein Lookahead) für jeden Timeframe (1D/4h/1h):
  - Level-State (SEEK / L1 / BOARD1 / L2 / BOARD2 / L3) + cyc_dir (+1 Rises / -1 Drops)
  - EMA50/200/800 des TF, Vektor-Flag (Vol >= mult*SMA10)
  - kausale ZigZag-Swings (rev% pro TF)
Plus zeit-verankerte Key-Levels (HOW/LOW/HOD/LOD, Anker 17:00 NY, letzte abgeschlossene Periode).

NOCH KEINE ENTRIES — dieser Schritt validiert nur, ob die Level-Erkennung Sinn ergibt.
Spec: Multi-TF-Level-Engine-Spec.md
"""
import csv, sys, os, bisect
from dataclasses import dataclass, field

# --- ZigZag rev% pro TF (grob->fein). REV_MULT skaliert alle; REV_<TF> überschreibt einzeln. ---
_RM = float(os.environ.get('REV_MULT', '1.0'))
_BASE = {"1D": 0.06, "4h": 0.03, "1h": 0.015, "15m": 0.008}
REV = {tf: float(os.environ.get('REV_'+tf.upper(), b*_RM)) for tf, b in _BASE.items()}
# --- Vektor-Schwelle (Vol >= mult * SMA10). EIGENER Env-Name (NICHT VEC_MULT!),
#     sonst Kollision mit der M/W-P1/P3-Vektoroption der wm_sar-Engine. ---
VEC_MULT = float(os.environ.get('LV_VEC_MULT', '1.5'))
VOL_SMA  = 10
# --- EMA-Längen ---
E50, E200, E800 = 50, 200, 800
# --- TFs als Sekunden ---
TF_SEC = {"1D": 86400, "4h": 14400, "1h": 3600, "15m": 900}


@dataclass
class Bar:
    t: int; o: float; h: float; l: float; c: float; v: float = 0.0


def load_csv(path):
    bars = []
    with open(path, newline="") as f:
        r = csv.DictReader(f)
        cols = {c.lower(): c for c in r.fieldnames}
        col = lambda *ns: next(cols[n] for n in ns if n in cols)
        ct, co, ch, cl, cc = (col("time","timestamp","date"), col("open"),
                              col("high"), col("low"), col("close"))
        cv = next((cols[x] for x in ("volume","vol","v") if x in cols), None)
        for row in r:
            t = int(float(row[ct]))
            bars.append(Bar(t, float(row[co]), float(row[ch]), float(row[cl]),
                            float(row[cc]), float(row[cv]) if cv else 0.0))
    bars.sort(key=lambda b: b.t)
    return bars


def ema_series(vals, length):
    out, k, e = [], 2/(length+1), None
    for v in vals:
        e = v if e is None else v*k + e*(1-k)
        out.append(e)
    return out


def resample(bars, sec):
    """Kausales Resampling auf Bucket-Größe sec. Bucket-Close-Zeit = bucket_start+sec."""
    buckets = {}; order = []
    for b in bars:
        k = (b.t // sec) * sec
        if k not in buckets:
            buckets[k] = Bar(k, b.o, b.h, b.l, b.c, b.v); order.append(k)
        else:
            x = buckets[k]
            x.h = max(x.h, b.h); x.l = min(x.l, b.l); x.c = b.c; x.v += b.v
    hb = [buckets[k] for k in order]
    close_t = [k + sec for k in order]   # erst dann "geschlossen" & nutzbar
    return hb, close_t


def zigzag_causal(hb, rev):
    """Kausale ZigZag-Pivots. Gibt pro HTF-Bar-Index den Stand zurück:
       confirmed pivots-Liste (typ,preis,idx). Pivot wird an der Kerze fixiert,
       wo rev% gerissen wird. Kein Repaint."""
    pivots = []          # (typ: +1 High / -1 Low, preis, bar_idx_confirm)
    dirn = 0; hi = hb[0].h; lo = hb[0].l; hi_i = lo_i = 0
    piv_at = [None]*len(hb)   # Liste der bis-dahin confirmten Pivots je Index (nur Anzahl/letzte gebraucht)
    for j in range(len(hb)):
        b = hb[j]
        conf = False
        if dirn >= 0:
            if b.h > hi: hi, hi_i = b.h, j
            if b.l < hi*(1-rev):
                pivots.append((+1, hi, hi_i)); dirn = -1; lo, lo_i = b.l, j; conf = True
        if not conf and dirn <= 0:
            if b.l < lo: lo, lo_i = b.l, j
            if b.h > lo*(1+rev):
                pivots.append((-1, lo, lo_i)); dirn = +1; hi, hi_i = b.h, j; conf = True
        piv_at[j] = len(pivots)   # wie viele Pivots zum Schluss dieses Bars bestätigt sind
    return pivots, piv_at


# ---------- Level-State-Maschine pro TF ----------
# States: 0=SEEK 1=L1 2=BOARD1 3=L2 4=BOARD2 5=L3
SEEK, L1, BOARD1, L2, BOARD2, L3 = 0, 1, 2, 3, 4, 5
SNAME = {0:"SEEK",1:"L1",2:"BOARD1",3:"L2",4:"BOARD2",5:"L3"}

def level_state(hb, rev, mult):
    """Pro HTF-Bar: (state, cyc_dir, level_no). Kausal.
    cyc_dir aus MARKTSTRUKTUR (Break of Structure):
      - Trend +1, sobald ein Swing-Hoch das vorige überbietet (Higher High = BoS up).
      - Trend -1, sobald ein Swing-Tief das vorige unterbietet (Lower Low = BoS down).
      - Trend persistiert bis zum Gegen-Break (stabil, nicht bei jedem Mini-Swing).
    Level-Count (in Trendrichtung):
      - SEEK->L1: erster Vektor-Bruch der 50EMA in Trendrichtung nach BoS.
      - Pullback-Pivot (Tief im Up / Hoch im Down) = BOARD, macht 'free' für nächstes Level.
      - BOARD->L2->L3 je nächster Vektor-Bruch. Reset bei BoS-Flip.
    """
    n = len(hb)
    closes = [b.c for b in hb]
    e50 = ema_series(closes, E50)
    vsma = [ (sum(x.v for x in hb[max(0,j-VOL_SMA):j])/max(1,len(hb[max(0,j-VOL_SMA):j]))) for j in range(n) ]
    pivots, piv_at = zigzag_causal(hb, rev)

    st = [SEEK]*n; cd = [0]*n; lv = [0]*n
    state = SEEK; trend = 0; level = 0; free = True
    prevSH = prevSL = None; npiv = 0
    for j in range(n):
        b = hb[j]; e = e50[j]
        vec = vsma[j] > 0 and b.v >= mult*vsma[j]
        # neu bestätigte Pivots verarbeiten (Marktstruktur)
        while npiv < piv_at[j]:
            ptyp, ppx, _ = pivots[npiv]; npiv += 1
            if ptyp == +1:                       # Swing-Hoch bestätigt
                bos_up = (prevSH is not None and ppx > prevSH)
                prevSH = ppx
                if bos_up and trend != 1:
                    trend = 1; level = 0; state = SEEK; free = True
                elif trend == -1:                # Top der Gegenrally im Downtrend = Board
                    if state in (L1, L2): state = BOARD1 if state == L1 else BOARD2
                    free = True
            else:                                # Swing-Tief bestätigt
                bos_dn = (prevSL is not None and ppx < prevSL)
                prevSL = ppx
                if bos_dn and trend != -1:
                    trend = -1; level = 0; state = SEEK; free = True
                elif trend == 1:                 # Boden des Pullbacks im Uptrend = Board
                    if state in (L1, L2): state = BOARD1 if state == L1 else BOARD2
                    free = True
        # Level-Break: Vektor + Close jenseits 50EMA in Trendrichtung, nur wenn 'free'
        if trend != 0 and vec and free:
            beyond = (trend == 1 and b.c > e) or (trend == -1 and b.c < e)
            if beyond:
                if state == SEEK and level == 0: level = 1; state = L1; free = False
                elif state == BOARD1:            level = 2; state = L2; free = False
                elif state == BOARD2:            level = 3; state = L3; free = False
        st[j] = state; cd[j] = trend; lv[j] = level
    return st, cd, lv, e50, ema_series(closes,E200), ema_series(closes,E800), pivots


# ---------- Zeit-verankerte Key-Levels (HOW/LOW/HOD/LOD) ----------
def ny_offset(ts):
    """grobe NY-DST: EDT (UTC-4) Mär..Nov, sonst EST (UTC-5). Reicht für Anker."""
    import datetime as dt
    d = dt.datetime.utcfromtimestamp(ts)
    return -4*3600 if 3 <= d.month <= 11 else -5*3600

def key_levels(bars):
    """Pro 15m-Bar: (HOD,LOD,HOW,LOW) der letzten ABGESCHLOSSENEN Periode.
    Tag/Woche-Anker 17:00 NY. Woche beginnt So 17:00 NY."""
    import datetime as dt
    # Tages-/Wochen-Buckets per Anker
    def day_key(ts):
        off = ny_offset(ts); loc = ts + off
        # 17:00 NY = Tageswechsel -> verschiebe um -17h, dann floor auf Tag
        return ((loc - 17*3600)//86400)
    def week_key(ts):
        off = ny_offset(ts); loc = ts + off
        # Wochenanker So 17:00 NY: shift so dass So17 -> 0
        shifted = loc - 17*3600
        # Unix epoch 1970-01-01 war Donnerstag; So = +3 Tage. Woche = floor((shifted - 3d)/7d)
        return ((shifted - 3*86400)//(7*86400))
    dHi={}; dLo={}; wHi={}; wLo={}
    for b in bars:
        dk=day_key(b.t); wk=week_key(b.t)
        dHi[dk]=max(dHi.get(dk,-1e18), b.h); dLo[dk]=min(dLo.get(dk,1e18), b.l)
        wHi[wk]=max(wHi.get(wk,-1e18), b.h); wLo[wk]=min(wLo.get(wk,1e18), b.l)
    out=[]
    for b in bars:
        dk=day_key(b.t); wk=week_key(b.t)
        HOD = dHi.get(dk-1); LOD = dLo.get(dk-1)
        HOW = wHi.get(wk-1); LOW = wLo.get(wk-1)
        out.append((HOD,LOD,HOW,LOW))
    return out


def efficiency_ratio(closes, N):
    """Kaufman Efficiency Ratio pro Bar (kausal): |net| / sum(|step|) ueber N.
    Hoch (->1) = sauberer Richtungslauf (klare Levels); niedrig (->0) = Chop."""
    n=len(closes); er=[0.0]*n
    for j in range(n):
        if j<N: continue
        net=abs(closes[j]-closes[j-N])
        vol=sum(abs(closes[k]-closes[k-1]) for k in range(j-N+1, j+1))
        er[j]= net/vol if vol>0 else 0.0
    return er

ER_N = int(os.environ.get('ER_N','30'))   # ER-Fenster pro TF (in TF-Bars)

def map_to_15m(bars, close_t, *series):
    """Mappt HTF-Serien auf 15m-Bars: letzter GESCHLOSSENER HTF-Bar."""
    idx=[]
    for b in bars:
        p = bisect.bisect_right(close_t, b.t)-1
        idx.append(p)
    return [[ (s[p] if p>=0 else None) for p in idx] for s in series]


def build(path, tfs=("1D","4h","1h")):
    bars = load_csv(path)
    n=len(bars)
    res={}
    for tf in tfs:
        hb, ct = resample(bars, TF_SEC[tf])
        st,cd,lv,e50,e200,e800,piv = level_state(hb, REV[tf], VEC_MULT)
        er = efficiency_ratio([b.c for b in hb], ER_N)
        m_st,m_cd,m_lv,m_e50,m_e200,m_er = map_to_15m(bars, ct, st,cd,lv,e50,e200,er)
        res[tf]=dict(state=m_st,cyc=m_cd,level=m_lv,e50=m_e50,e200=m_e200,er=m_er,
                     nbars=len(hb),npiv=len(piv))
    kl = key_levels(bars)
    return bars, res, kl


# ---------------- DIAGNOSE ----------------
def diag(path):
    import datetime as dt
    bars, res, kl = build(path)
    n=len(bars)
    print(f"15m Bars: {n}  ({dt.datetime.utcfromtimestamp(bars[0].t):%Y-%m-%d} .. {dt.datetime.utcfromtimestamp(bars[-1].t):%Y-%m-%d})\n")
    for tf in ("1D","4h","1h"):
        r=res[tf]
        print(f"=== {tf}: {r['nbars']} HTF-Bars, {r['npiv']} ZigZag-Pivots ===")
        # State-Verteilung über 15m-Bars
        from collections import Counter
        cS=Counter(SNAME.get(s,'?') for s in r['state'] if s is not None)
        cC=Counter(r['cyc'])
        tot=sum(cS.values())
        sd=" ".join(f"{k}:{v/tot*100:.0f}%" for k,v in sorted(cS.items(),key=lambda x:-x[1]))
        print(f"  State-Verteilung: {sd}")
        print(f"  cyc_dir: Rises(+1) {cC.get(1,0)/n*100:.0f}%  Drops(-1) {cC.get(-1,0)/n*100:.0f}%  unklar(0) {cC.get(0,0)/n*100:.0f}%")
        # Sanity: stimmt cyc_dir grob mit e50>e200 überein?
        agree=sum(1 for i in range(n) if r['cyc'][i] and r['e50'][i] and r['e200'][i]
                  and ((r['cyc'][i]==1)==(r['e50'][i]>r['e200'][i])))
        nz=sum(1 for i in range(n) if r['cyc'][i] and r['e50'][i] and r['e200'][i])
        print(f"  cyc_dir stimmt mit EMA50>EMA200 überein: {agree/max(1,nz)*100:.0f}% (n={nz})")
        # Level-Verteilung
        cL=Counter(r['level'])
        print(f"  Level: L0 {cL.get(0,0)/n*100:.0f}%  L1 {cL.get(1,0)/n*100:.0f}%  L2 {cL.get(2,0)/n*100:.0f}%  L3 {cL.get(3,0)/n*100:.0f}%\n")
    # Key-Level Sanity (ein Beispieltag)
    mid=n//2
    HOD,LOD,HOW,LOW = kl[mid]
    b=bars[mid]
    print(f"Key-Level Beispiel @ {dt.datetime.utcfromtimestamp(b.t):%Y-%m-%d %H:%M} UTC  Preis {b.c:.0f}")
    print(f"  HOD {HOD:.0f}  LOD {LOD:.0f}  HOW {HOW:.0f}  LOW {LOW:.0f}")


if __name__ == "__main__":
    diag(sys.argv[1] if len(sys.argv)>1 else "backtest/data/BTCUSDT_15m_4y.csv")
