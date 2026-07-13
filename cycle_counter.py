#!/usr/bin/env python3
"""
TBD Zyklus-Zähler (kausal) — Baustein 1: EIN Timeframe.
Modell (Wookie, [[tbd-zyklus-zaehlung-modell]]):
  - Zyklus startet mit reset-M (Top->Down) / reset-W (Boden->Up). P1 = Invalidierung, FEST.
  - Level = neues tieferes Tief (Down) / höheres Hoch (Up). Höhere Tiefs/tiefere Hochs
    dazwischen = Board-Meeting (kein Level).
  - Reversal-M/W NUR nach 3 Levels: nach L3 ein höheres Tief (Down->Up) bzw. tieferes Hoch,
    bestätigt durch Bruch der Zwischen-Neckline -> Flip. Neues P1 = P1 des reversal-M/W.
  - Failsafe: Close jenseits P1 VOR L3 -> Zyklus ungültig.
Swings: kausaler ZigZag rev% (kein Repaint).
Abnahmetest: 1h 27.6.-1.7.2026 muss M-Top 27.6 17:00 -> L1/L2/L3 -> W-Flip reproduzieren.
"""
import csv, sys, os, datetime as dt

def load_csv(path):
    bars=[]
    with open(path,newline="") as f:
        r=csv.DictReader(f); cols={c.lower():c for c in r.fieldnames}
        col=lambda *ns: next(cols[n] for n in ns if n in cols)
        ct,co,ch,cl,cc=(col("time","timestamp"),col("open"),col("high"),col("low"),col("close"))
        cv=next((cols[x] for x in ("volume","vol","v") if x in cols),None)
        for row in r:
            bars.append((int(float(row[ct])),float(row[co]),float(row[ch]),float(row[cl]),float(row[cc]),float(row[cv]) if cv else 0.0))
    bars.sort(); return bars

def resample(bars, sec):
    bk={}; order=[]
    for t,o,h,l,c,v in bars:
        k=(t//sec)*sec
        if k not in bk: bk[k]=[k,o,h,l,c,v]; order.append(k)
        else: x=bk[k]; x[2]=max(x[2],h); x[3]=min(x[3],l); x[4]=c; x[5]+=v
    return [bk[k] for k in order]

def zigzag(hb, rev):
    """Kausale Pivots (typ +1 High/-1 Low, preis, idx-des-Extrems, idx-Bestätigung)."""
    piv=[]; dirn=0; hi=hb[0][2]; lo=hb[0][3]; hi_i=lo_i=0
    piv_at=[0]*len(hb)
    for j in range(len(hb)):
        h=hb[j][2]; l=hb[j][3]; conf=False
        if dirn>=0:
            if h>hi: hi,hi_i=h,j
            if l<hi*(1-rev): piv.append((+1,hi,hi_i,j)); dirn=-1; lo,lo_i=l,j; conf=True
        if not conf and dirn<=0:
            if l<lo: lo,lo_i=l,j
            if h>lo*(1+rev): piv.append((-1,lo,lo_i,j)); dirn=+1; hi,hi_i=h,j; conf=True
        piv_at[j]=len(piv)
    return piv, piv_at

def ema_series(vals, length):
    out=[]; k=2/(length+1); e=None
    for v in vals:
        e=v if e is None else v*k+e*(1-k); out.append(e)
    return out

def u2(t): return dt.datetime.utcfromtimestamp(t+7200).strftime('%d.%m %H:%M')

def count(hb, rev, t0=None, t1=None, verbose=True):
    """Symmetrisch für Down (d=-1) und Up (d=+1).
    Level = neues Extrem in Trendrichtung; Gegen-Pivot = Board-Meeting.
    Reversal NUR nach L3: Gegen-Extrem (höheres Tief / tieferes Hoch) + Neckline-Bruch -> Flip.
    Failsafe: Close jenseits P1 vor L3 -> SEEK."""
    piv,piv_at=zigzag(hb,rev)
    e50=ema_series([b[4] for b in hb],50)
    vol=[b[5] for b in hb]
    vsma=[(sum(vol[max(0,j-10):j])/max(1,len(vol[max(0,j-10):j]))) for j in range(len(hb))]
    VMULT=float(os.environ.get('VMULT','1.5'))   # Mindest-Spike vs SMA (Floor)
    VFRAC=float(os.environ.get('VFRAC','0.7'))   # Level-Vol >= VFRAC * Vol des Vorlevels (Klimax-Progression)
    def lvol(ei):                        # Klimax-Volumen nahe der Extremstelle
        w=vol[max(0,ei-2):ei+3]; return max(w) if w else 0.0
    def vspike(ei):                      # Mindest-Spike vs lokalem Schnitt
        return vsma[ei]>0 and lvol(ei)>=VMULT*vsma[ei]
    def vol_ok(ei, prev):                # gültiges Level-Ende?
        return vspike(ei) and (prev is None or lvol(ei)>=VFRAC*prev)
    n=len(hb); ev=[]; d_arr=[0]*n; lvl_arr=[0]*n
    state='SEEK'; d=0; p1=None; level=0; ext=None; lastvol=None
    lastH=lastH2=None; lastL=lastL2=None
    trough=None; peak=None          # Zwischen-Extrem für M/W-Bootstrap
    rev_neck=None; armed=False      # Reversal nach L3
    retraced=False                  # Board-Meeting: Retrace an 50EMA seit letztem Level?
    npiv=0
    def log(tag,px,j):
        e=(u2(hb[j][0]),tag,round(px)); ev.append(e)
        if verbose and (t0 is None or t0<=hb[j][0]<=t1): print(f'  {e[0]}  {tag:<12} {round(px)}')
    for j in range(n):
        c=hb[j][4]
        # Board-Meeting-Detektion: Retrace an die 50EMA seit letztem Level
        if state=='CYCLE':
            if d==-1 and hb[j][2]>=e50[j]: retraced=True
            elif d==+1 and hb[j][3]<=e50[j]: retraced=True
        while npiv<piv_at[j]:
            typ,px,ei,ci=piv[npiv]; npiv+=1
            if typ==+1:                          # ---- Swing-Hoch ----
                lastH2=lastH; lastH=px
                if state=='SEEK':
                    trough=lastL                 # Neckline-Kandidat für M
                    # W-Bootstrap: höheres Tief + Bruch über Zwischen-Hoch (peak)
                    if lastL is not None and lastL2 is not None and lastL>lastL2 and peak is not None and px>peak:
                        state='CYCLE'; d=+1; p1=lastL2; level=1; ext=px; armed=False; retraced=False; lastvol=lvol(ei)
                        log('RESET-W P1',p1,j); log('L1',px,j)
                elif state=='CYCLE':
                    if d==+1:
                        if ext is None:                 # erstes Hoch = L1
                            level=1; ext=px; retraced=False; lastvol=lvol(ei); log('L1',px,j)
                        elif px>ext:                    # neues höheres Hoch
                            if retraced and vol_ok(ei,lastvol): level+=1; ext=px; retraced=False; lastvol=lvol(ei); log(f'L{level}' if level<=3 else f'ext{level}',px,j)
                            else: ext=px                # gleiches Level verlängern (kein Board-Meeting/SVC)
                        else:
                            if level>=3: armed=True     # tieferes Hoch nach L3 (Reversal-M P3)
                    else:                        # d==-1: Hoch im Down = Board / Reversal-Neckline
                        if level>=3: rev_neck=px
            else:                                # ---- Swing-Tief ----
                lastL2=lastL; lastL=px
                if state=='SEEK':
                    peak=lastH                   # Neckline-Kandidat für W
                    # M-Bootstrap: tieferes Hoch + Bruch unter Zwischen-Tief (trough)
                    if lastH is not None and lastH2 is not None and lastH<lastH2 and trough is not None and px<trough:
                        state='CYCLE'; d=-1; p1=lastH2; level=1; ext=px; armed=False; retraced=False; lastvol=lvol(ei)
                        log('RESET-M P1',p1,j); log('L1',px,j)
                elif state=='CYCLE':
                    if d==-1:
                        if ext is None:                     # erstes Tief = L1
                            level=1; ext=px; retraced=False; lastvol=lvol(ei); log('L1',px,j)
                        elif px<ext:                        # neues tieferes Tief
                            if retraced and vol_ok(ei,lastvol): level+=1; ext=px; retraced=False; lastvol=lvol(ei); log(f'L{level}' if level<=3 else f'ext{level}',px,j)
                            else: ext=px                    # gleiches Level verlängern (kein Board-Meeting/SVC)
                        else:
                            if level>=3: armed=True         # höheres Tief nach L3
                    else:                        # d==+1: Tief im Up = Board / Reversal-Neckline
                        if level>=3: rev_neck=px
        # ---- Reversal-Flip (Close bricht Neckline nach L3 + Gegen-Extrem) ----
        if state=='CYCLE' and level>=3 and rev_neck is not None:
            if d==-1 and armed and c>rev_neck:
                log('W-FLIP -> UP',c,j); state='CYCLE'; d=+1; p1=ext; level=0; ext=None
                lastH=lastH2=lastL=lastL2=None; rev_neck=None; armed=False; peak=None; trough=None; retraced=False; lastvol=None
            elif d==+1 and armed and c<rev_neck:
                log('M-FLIP -> DOWN',c,j); state='CYCLE'; d=-1; p1=ext; level=0; ext=None
                lastH=lastH2=lastL=lastL2=None; rev_neck=None; armed=False; peak=None; trough=None; retraced=False; lastvol=None
        # UP: höheres Hoch reset armed-Neckline (nur Gegen-Extrem = tieferes Hoch zählt)
        if state=='CYCLE' and level>=3:
            pass
        # ---- Failsafe: Close jenseits P1 vor L3 ----
        if state=='CYCLE' and p1 is not None and level<3:
            if (d==-1 and c>p1) or (d==+1 and c<p1):
                log('INVALID (Close>P1)' if d==-1 else 'INVALID (Close<P1)',c,j)
                state='SEEK'; d=0; level=0; ext=None; armed=False; rev_neck=None
        d_arr[j]=d; lvl_arr[j]=level
    return ev, d_arr, lvl_arr

import bisect as _bs
REV_TF={86400:0.08, 14400:0.04, 3600:0.015, 900:0.008}   # grobe rev pro TF-Sekunden

def dir_level_for_base(base_bars, sec, rev=None):
    """Gibt pro Basis-Bar (dir, level) des Zyklus auf TF `sec`, kausal gemappt.
    base_bars: Liste (t,o,h,l,c,v). rev: sonst REV_TF[sec]."""
    if rev is None: rev=REV_TF.get(sec,0.02)
    hb=resample(base_bars,sec)
    ev,d_arr,lvl_arr=count(hb,rev,verbose=False)
    close_t=[b[0]+sec for b in hb]
    od=[]; ol=[]
    for row in base_bars:
        p=_bs.bisect_right(close_t,row[0])-1
        od.append(d_arr[p] if p>=0 else 0); ol.append(lvl_arr[p] if p>=0 else 0)
    return od, ol

if __name__=="__main__":
    path=sys.argv[1] if len(sys.argv)>1 else "backtest/data/BTCUSDT_15m_4y.csv"
    tf=int(os.environ.get('TF_SEC','3600')); rev=float(os.environ.get('REV','0.010'))
    bars=load_csv(path); hb=resample(bars,tf)
    t0=int(dt.datetime(2026,6,26).timestamp()); t1=int(dt.datetime(2026,7,3).timestamp())
    print(f"Zyklus-Zähler TF={tf}s rev={rev}  Fenster 26.6-3.7:")
    count(hb,rev,t0,t1)
