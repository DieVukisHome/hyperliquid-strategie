import os
import os
#!/usr/bin/env python3
"""
W/M SAR Backtester v16 — wie v16, plus: P1/P3 = Inverted Hammer/Hammer ODER Vektorkerze; leichte EMA-Touch-Toleranz.

Idee (Wookie): TP1 bei 3R -> 75% schliessen, Runner (25%) laeuft weiter. Danach ist man "offen
fuer einen neuen Trade": ein neues gleichgerichtetes M/W oeffnet einen NEUEN Lot (Pyramiding in
eine Netto-Position). Ein Gegen-M/W flippt ALLES (One-Way: long+short gleichzeitig unmoeglich
auf Hyperliquid).

Modell:
  - Es gibt zu jeder Zeit höchstens EINEN aktiven (pre-TP1) Lot. Solange er pre-TP1 ist, zieht
    ein gleichgerichtetes Signal nur dessen Stop nach (Trail), kein neuer Lot.
  - Sobald er TP1 (3R) erreicht (75% zu), wird er Runner; dann oeffnet das NAECHSTE
    gleichgerichtete Signal einen neuen Lot. So entsteht kontrolliertes Pyramiding.
  - Gegen-Signal: alle Lots schliessen + neuer Lot in Gegenrichtung.
  - Jeder Lot: 1% Risk (=1R), SL=P1 inkl. Wick, Runner trailt per SAR (Label-Kerze), 10x-Cap.

Erkennung identisch v13 (P1->P2->P3, Fib-0,618, Docht-Filter, P3=Body-Extrem seit P2, P1-Break).
"""
import csv
import sys
from dataclasses import dataclass

import os as _os0
PIV         = int(_os0.environ.get('PIV','4'))
MW_MIN      = int(_os0.environ.get('MW_MIN','4'))
MW_MAX      = int(_os0.environ.get('MW_MAX','60'))
FIB         = 0.618
WICK_FRAC   = 0.50
EMA_LEN     = 50
REV_WICK    = 0.50
REV_BODY    = 0.40
TP1_R       = float(os.environ.get('TP1_R','100.0'))   # 100 = praktisch nie -> reine Runner
TP1_FRAC    = float(os.environ.get('TP1_FRAC','0.75')) # Anteil der bei TP1 geschlossen wird
COMMISSION  = 0.00045
INIT_CAP    = 10000.0
LOOKBACK_D  = 1600
RISK        = float(os.environ.get('RISK','0.01'))
VT_ON       = os.environ.get('VT_ON','0')=='1'       # Vol-Targeting Overlay
VT_N        = int(os.environ.get('VT_N','96'))       # Vola-Fenster (96*15m = 1 Tag)
VT_LO       = float(os.environ.get('VT_LO','0.3'))   # Size-Clip unten
VT_HI       = float(os.environ.get('VT_HI','1.5'))   # Size-Clip oben
RO_ON       = os.environ.get('RO_ON','0')=='1'
RO_K        = int(os.environ.get('RO_K','8'))
RO_TH       = float(os.environ.get('RO_TH','0.0'))
RO_LOW      = float(os.environ.get('RO_LOW','0.3'))
MTF_ON      = os.environ.get('MTF_ON','0')=='1'
MTF_MACRO   = os.environ.get('MTF_MACRO','1')=='1'   # 1D-Makro muss With-Trend mit-tragen
BIAS_MODE   = os.environ.get('BIAS_MODE','h4')       # h4 = 4h-Bias | conf = 1D&4h-Konfluenz
ER_MIN      = float(os.environ.get('ER_MIN','0.0'))  # Mindest-Clarity zum Entry
ER_TF       = os.environ.get('ER_TF','4h')           # TF fuer den Clarity-Filter (4h|1h|1D); Fenster = ER_N Bars dieses TF
CC_BIAS     = os.environ.get('CC_BIAS','0')=='1'     # Bias/Level aus Zyklus-Zähler (cycle_counter) statt levels_mtf-BoS
DIAG_T0     = int(os.environ.get('DIAG_T0','0'))     # Diagnose-Fenster (nur Ausgabe, keine Logik)
DIAG_T1     = int(os.environ.get('DIAG_T1','0'))
MTF_RBTOL   = float(os.environ.get('MTF_RBTOL','0.005'))  # Roadblock-Naehe-Toleranz
RB_MODE     = os.environ.get('RB_MODE','off')    # off|band|reclaim — Verschärfung Reversal-Roadblock (TBD: Docht durch Level ok, Vollkörper-Close jenseits = ungültig)
RB_BAND     = float(os.environ.get('RB_BAND','0.02'))   # band: Close max X% JENSEITS des Levels (kein fallendes Messer)
RB_LB       = int(os.environ.get('RB_LB','16'))         # reclaim: Level muss in letzten N Bars touchiert worden sein
REV_VOL     = float(os.environ.get('REV_VOL','0'))      # SVC-Proxy: Reversal-Signalkerze braucht Vol >= X*SMA10 (0=aus)
BCR_WT_ONLY = os.environ.get('BCR_WT_ONLY','0')=='1'    # BCR = Continuation-Pattern -> nur with-trend, nie als Reversal (TBD)
BE_R        = float(os.environ.get('BE_R','0'))         # SL->Entry sobald +X R erreicht (0=aus)
TS_D        = float(os.environ.get('TS_D','0'))         # Time-Stop: nach X Tagen unter TS_R -> raus (0=aus)
TS_R        = float(os.environ.get('TS_R','1.0'))       # R-Schwelle fuer den Time-Stop
EXIT_RAW    = os.environ.get('EXIT_RAW','off')          # off|mw|all — Gegensignal schliesst Position auch wenn Entry-Gate es blockt
TP1R_ENV    = float(os.environ.get('TP1_R','0'))        # >0: TP1 bei X R (Anteil TP1_FRAC), sonst reiner Runner
TP1F_ENV    = float(os.environ.get('TP1_FRAC','0'))

# Signal-Capture (Live-Watcher/Diagnose): run() fuellt LAST_SIGNALS mit ALLEN
# Signal-Events inkl. Gate-Entscheidung ('pass' oder Block-Grund) + Kontext.
LAST_SIGNALS = []
TDIR_ON     = os.environ.get('TDIR_ON','0')=='1'
TDIR_MODE   = os.environ.get('TDIR_MODE','slope')   # slope|ema800|stack
TDIR_N      = int(os.environ.get('TDIR_N','480'))
TDIR_TH     = float(os.environ.get('TDIR_TH','0.0'))
MAX_LEV     = float(os.environ.get('MAX_LEV','10.0'))
VOL_SMA_LEN = 10       # Schnitt-Volumen-Fenster
import os
VEC_MULT    = float(os.environ.get('VEC_MULT','99.0'))
BCR_ON      = os.environ.get('BCR_ON','0')=='1'
MW_ON       = os.environ.get('MW_ON','1')=='1'
BCR_VEC     = float(os.environ.get('BCR_VEC','1.5'))
BCR_WIN     = int(os.environ.get('BCR_WIN','120'))
BCR_TOL     = float(os.environ.get('BCR_TOL','0.0015'))
BCR_NECK    = os.environ.get('BCR_NECK','1')=='1'
BCR_200     = os.environ.get('BCR_200','0')=='1'
BCR_200TOL  = float(os.environ.get('BCR_200TOL','0.01'))
BCR_200MODE = os.environ.get('BCR_200MODE','bar')   # bar = aktuelle Kerze | since = Touch irgendwann seit Break | sinceswap = Seiten vertauscht (Server-Bug-Check)
BCR_MINRT   = int(os.environ.get('BCR_MINRT','0'))  # Retest fruehestens N Bars nach dem Break (0=aus; vgl. min_retest_bars der 5m-Engine)
MW1H_SIG    = os.environ.get('MW1H_SIG','0')=='1'   # 1h-M/W als eigene Signalquelle (tag mw1h, fraktal gleiche Detektion)
BCR_REV_1H  = float(os.environ.get('BCR_REV_1H','0')) # bcr/rev erlaubt, wenn 1h-M/W gleicher Richtung binnen X Stunden bestaetigt (0=aus)
BCR_HAM     = os.environ.get('BCR_HAM','1')=='1'
BCR_FALLBACK= os.environ.get('BCR_FALLBACK','1')=='1'
BCR_FLAT    = os.environ.get('BCR_FLAT','0')=='1'
NOPYR       = os.environ.get('NOPYR','0')=='1'
VEC_WICK    = float(os.environ.get('VEC_WICK','0.40'))
HTF_ON      = os.environ.get('HTF_ON','0')=='1'
E200_ON     = os.environ.get('E200_ON','0')=='1'
SLOPE_ON    = os.environ.get('SLOPE_ON','0')=='1'
SLOPE_N     = int(os.environ.get('SLOPE_N','80'))
SLOPE_TH    = float(os.environ.get('SLOPE_TH','0'))
EMA200_LEN  = int(os.environ.get('EMA200_LEN','200'))
CTE_ON      = os.environ.get('CTE_ON','0')=='1'
CTE_N       = int(os.environ.get('CTE_N','160'))
CTE_TH      = float(os.environ.get('CTE_TH','0.004'))
CTE_TOL     = float(os.environ.get('CTE_TOL','0.0015'))
CTE_SWLB    = int(os.environ.get('CTE_SWLB','20'))
CTE_SEP     = float(os.environ.get('CTE_SEP','0.0'))
REGIME_ON   = os.environ.get('REGIME_ON','0')=='1'
REG_TH      = float(os.environ.get('REG_TH','0.006'))
REG_SEP     = float(os.environ.get('REG_SEP','0.005'))
BCR_SLMODE  = os.environ.get('BCR_SLMODE','p3')
BCR_SLLB    = int(os.environ.get('BCR_SLLB','10'))
BCR_SWLB    = int(os.environ.get('BCR_SWLB','20'))
EMA_TOL     = 0.0005   # P2: EMA-Berührung mit 0,05% Toleranz


@dataclass
class Bar:
    t: int; o: float; h: float; l: float; c: float; v: float = 0.0


def load_csv(path):
    bars = []
    with open(path, newline="") as f:
        r = csv.DictReader(f)
        cols = {c.lower(): c for c in r.fieldnames}
        def col(*names):
            for n in names:
                if n in cols:
                    return cols[n]
            raise KeyError(f"Spalte fehlt: {names}")
        ct, co, ch, cl, cc = (col("time", "timestamp", "date", "datetime"),
                              col("open", "o"), col("high", "h"),
                              col("low", "l"), col("close", "c"))
        cv = next((cols[x] for x in ("volume","vol","v") if x in cols), None)
        for row in r:
            tv = row[ct]
            try:
                t = int(float(tv))
            except ValueError:
                import datetime as dt
                t = int(dt.datetime.fromisoformat(tv.replace("Z", "+00:00")).timestamp())
            bars.append(Bar(t, float(row[co]), float(row[ch]), float(row[cl]), float(row[cc]), float(row[cv]) if cv else 0.0))
    bars.sort(key=lambda b: b.t)
    return bars


def ema_series(values, length):
    out, k, e = [], 2 / (length + 1), None
    for v in values:
        e = v if e is None else v * k + e * (1 - k)
        out.append(e)
    return out


def is_hammer(b):
    rng = b.h - b.l
    if rng <= 0:
        return False
    return (min(b.o, b.c) - b.l) >= REV_WICK * rng and abs(b.c - b.o) <= REV_BODY * rng


def is_inv_hammer(b):
    rng = b.h - b.l
    if rng <= 0:
        return False
    return (b.h - max(b.o, b.c)) >= REV_WICK * rng and abs(b.c - b.o) <= REV_BODY * rng


def m_wick_limit(b):
    return max(b.o, b.c) + WICK_FRAC * (b.h - max(b.o, b.c))


def w_wick_limit(b):
    return min(b.o, b.c) - WICK_FRAC * (min(b.o, b.c) - b.l)


def detect_mw_htf(hb):
    """M/W-Detektion (identische v13-Logik, ohne Vektor-Option) auf HTF-Bars.
    Liefert [(bar_idx, dir, p1_level)] — dir +1 = W (Long), -1 = M (Short)."""
    n = len(hb)
    highsH = [b.h for b in hb]; lowsH = [b.l for b in hb]
    emaH = ema_series([b.c for b in hb], EMA_LEN)
    out = []
    mp1 = mp1bar = mp2bar = m_trough = m_wl = m_p2peak = None
    wp1v = wp1bar = wp2bar = w_peak = w_wl = w_p2trough = None
    for i in range(n):
        b = hb[i]; e = emaH[i]
        if i < PIV:
            continue
        ih = is_inv_hammer(b); ha = is_hammer(b)
        locHigh = b.h >= max(highsH[i-PIV:i]); locLow = b.l <= min(lowsH[i-PIV:i])
        # M
        if mp1 is None:
            if ih and locHigh and b.c > e:
                mp1, mp1bar, mp2bar, m_trough, m_wl = b.h, i, None, b.l, m_wick_limit(b)
        else:
            if b.h > mp1:
                if ih and locHigh and b.c > e:
                    mp1, mp1bar, mp2bar, m_trough, m_wl = b.h, i, None, b.l, m_wick_limit(b)
                else:
                    mp1 = None; mp2bar = None
            elif (i - mp1bar) > MW_MAX:
                mp1 = None; mp2bar = None
            else:
                m_trough = min(m_trough, b.l)
                if mp2bar is None:
                    if (i - mp1bar) >= MW_MIN and b.l <= e * (1 + EMA_TOL):
                        mp2bar = i; m_p2peak = b.c
                else:
                    fib = m_trough + FIB * (mp1 - m_trough)
                    if (i - mp2bar) >= MW_MIN and ih and locHigh and b.c > e and b.h <= mp1 \
                            and b.h >= fib and b.h <= m_wl and b.h >= m_p2peak and b.c < mp1:
                        out.append((i, -1, mp1)); mp1 = None; mp2bar = None
                    else:
                        m_p2peak = max(m_p2peak, b.c)
        # W
        if wp1v is None:
            if ha and locLow and b.c < e:
                wp1v, wp1bar, wp2bar, w_peak, w_wl = b.l, i, None, b.h, w_wick_limit(b)
        else:
            if b.l < wp1v:
                if ha and locLow and b.c < e:
                    wp1v, wp1bar, wp2bar, w_peak, w_wl = b.l, i, None, b.h, w_wick_limit(b)
                else:
                    wp1v = None; wp2bar = None
            elif (i - wp1bar) > MW_MAX:
                wp1v = None; wp2bar = None
            else:
                w_peak = max(w_peak, b.h)
                if wp2bar is None:
                    if (i - wp1bar) >= MW_MIN and b.h >= e * (1 - EMA_TOL):
                        wp2bar = i; w_p2trough = b.c
                else:
                    fib = w_peak - FIB * (w_peak - wp1v)
                    if (i - wp2bar) >= MW_MIN and ha and locLow and b.c < e and b.l >= wp1v \
                            and b.l <= fib and b.l >= w_wl and b.l <= w_p2trough and b.c > wp1v:
                        out.append((i, 1, wp1v)); wp1v = None; wp2bar = None
                    else:
                        w_p2trough = min(w_p2trough, b.c)
    return out


@dataclass
class Trade:
    dir: int; entry_t: int; entry: float
    exit_t: int = 0; exit: float = 0.0; reason: str = ""
    r: float = 0.0; equity_after: float = 0.0; tag: str = ""


class Lot:
    __slots__ = ("dir","entry","entry_t","sl","sl_init","qty_total","qty_open",
                 "realized","partial_done","tp1","eq_entry","risk_pu","tag")


def run(bars, log_window=None):
    global LAST_SIGNALS
    LAST_SIGNALS = []
    def _sig_rec(ev, gate):
        ev['gate'] = gate; LAST_SIGNALS.append(ev)
    highs = [b.h for b in bars]
    lows  = [b.l for b in bars]
    ema   = ema_series([b.c for b in bars], EMA_LEN)
    ema200= ema_series([b.c for b in bars], EMA200_LEN)
    import bisect as _bs
    bias=[0]*len(bars)
    if HTF_ON:
        hrs={}; order=[]
        for b in bars:
            h=(b.t//3600)*3600
            if h not in hrs: hrs[h]=[b.c,b.v]; order.append(h)
            else: hrs[h]=[b.c,hrs[h][1]+b.v]
        hc=[hrs[h][0] for h in order]; hv=[hrs[h][1] for h in order]
        he=[0.0]*len(order); kk=2/51
        for j in range(len(order)): he[j]=hc[j] if j==0 else hc[j]*kk+he[j-1]*(1-kk)
        ct=[]; bs=[]; cur=0
        for j in range(len(order)):
            sm=sum(hv[max(0,j-9):j+1])/min(10,j+1)
            vecH = sm>0 and hv[j]>=1.5*sm
            if vecH: cur = 1 if hc[j]>he[j] else (-1 if hc[j]<he[j] else cur)
            ct.append(order[j]+3600); bs.append(cur)
        for i in range(len(bars)):
            p=_bs.bisect_right(ct,bars[i].t)-1
            bias[i]= bs[p] if p>=0 else 0
    n = len(bars)
    vol_sma = [ (sum(x.v for x in bars[max(0,i-VOL_SMA_LEN):i]) / max(1,len(bars[max(0,i-VOL_SMA_LEN):i]))) for i in range(n) ]
    now = bars[-1].t
    win_start = now - LOOKBACK_D * 86400

    # --- Multi-TF Level-Kontext (levels_mtf) ---
    _ctx = {}; _kl = None
    if MTF_ON:
        import levels_mtf as _LV
        for tf in ('1D','4h','1h'):
            hb, ct = _LV.resample(bars, _LV.TF_SEC[tf])
            st, cd, lv, *_ = _LV.level_state(hb, _LV.REV[tf], _LV.VEC_MULT)
            er = _LV.efficiency_ratio([bb.c for bb in hb], _LV.ER_N)
            m = _LV.map_to_15m(bars, ct, st, cd, lv, er)
            _ctx[tf] = dict(state=m[0], cyc=m[1], level=m[2], er=m[3])
        _kl = _LV.key_levels(bars)
        _cc_d1=_cc_d4=_cc_l4=_cc_d1h=_cc_l1h=None
        if CC_BIAS:
            import cycle_counter as _CC
            _bt=[(b.t,b.o,b.h,b.l,b.c,b.v) for b in bars]
            _cc_d1,_=_CC.dir_level_for_base(_bt,86400)
            _cc_d4,_cc_l4=_CC.dir_level_for_base(_bt,14400)
            _cc_d1h,_cc_l1h=_CC.dir_level_for_base(_bt,3600)

    # --- 1h-M/W-Signale (fraktale Detektion auf 1h-Resample, kausal ab Bucket-Close) ---
    _mw1h = []; _mw1h_ptr = 0; _last1hM = -1e18; _last1hW = -1e18
    if MW1H_SIG or BCR_REV_1H > 0:
        import levels_mtf as _LV1
        hb1, ct1 = _LV1.resample(bars, 3600)
        for (j, dh, p1) in detect_mw_htf(hb1):
            _mw1h.append((ct1[j], dh, p1))   # nutzbar ab Close des 1h-Buckets
        _mw1h.sort()

    # --- Vol-Targeting: Vola = SMA der relativen Bar-Range ---
    _vt = None; _vtmed = 0.0; _vt_now = 1.0
    if VT_ON:
        _rng = [ (bb.h-bb.l)/bb.c if bb.c>0 else 0.0 for bb in bars ]
        _vt = [0.0]*n
        for k in range(n):
            w = _rng[max(0,k-VT_N+1):k+1]; _vt[k] = sum(w)/max(1,len(w))
        import statistics as _stx
        _vtmed = _stx.median([x for x in _vt if x>0]) or 0.0

    # Detection-State (v13)
    mp1 = mp1bar = mp2bar = m_trough = m_wl = m_p2peak = None
    wp1v = wp1bar = wp2bar = w_peak = w_wl = w_p2trough = None

    _ema800= ema_series([b.c for b in bars], 800) if 'ema_series' in dir() else None
    lots = []
    prevM_high = None; prevW_low = None
    wp2_prev=None; mp2_prev=None
    cL=None  # {'bar','neck','p3','broke','exp'}
    cS=None
    equity = INIT_CAP; peak = INIT_CAP; max_dd = 0.0
    trades = []
    max_conc = 0

    import datetime as _dt
    def _u2(t): return _dt.datetime.utcfromtimestamp(t + 7200).strftime("%d.%m %H:%M")
    def Lg(t, *m):
        if log_window and log_window[0] <= t <= log_window[1]:
            print(f"  {_u2(t)} ", *m)

    def _size_factor():
        if not RO_ON or len(trades)<RO_K: return 1.0
        return RO_LOW if sum(tt.r for tt in trades[-RO_K:])< RO_TH else 1.0
    def open_lot(d, px, t, sl0, tag=''):
        nonlocal equity
        risk_pu = abs(px - sl0)
        if risk_pu <= 0:
            return
        q = (equity * RISK * _size_factor() * _vt_now) / risk_pu
        q = min(q, MAX_LEV * equity / px)
        L = Lot()
        L.tag = tag
        L.dir = d; L.entry = px; L.entry_t = t; L.sl = sl0; L.sl_init = sl0
        L.qty_total = q; L.qty_open = q; L.realized = 0.0; L.partial_done = False
        L.tp1 = px + d * TP1_R * risk_pu; L.eq_entry = equity; L.risk_pu = risk_pu
        lots.append(L)
        Lg(t, f"OPEN {'LONG' if d==1 else 'SHORT'} #{len(lots)} @{px:.1f} SL{sl0:.1f} TP1 {L.tp1:.1f}")

    def take_tp1(L, t):
        nonlocal equity
        qp = L.qty_total * TP1_FRAC
        net = (L.tp1 - L.entry) * qp * L.dir - (L.entry + L.tp1) * qp * COMMISSION
        L.realized += net; equity += net
        L.qty_open -= qp; L.partial_done = True; L.sl = L.entry
        Lg(t, f"TP1 {'L' if L.dir==1 else 'S'} @{L.tp1:.1f} (+{TP1_R:.0f}R {int(TP1_FRAC*100)}%), SL->BE")

    def close_lot(L, px, t, reason):
        nonlocal equity
        rest = (px - L.entry) * L.qty_open * L.dir - (L.entry + px) * L.qty_open * COMMISSION
        equity += rest
        total = L.realized + rest
        denom = L.risk_pu * L.qty_total
        r = total / denom if denom > 0 else 0.0
        trades.append(Trade(L.dir, L.entry_t, L.entry, t, px, reason, r, equity, getattr(L, 'tag', '')))
        Lg(t, f"CLOSE {'L' if L.dir==1 else 'S'} @{px:.1f} ({reason}) r={r:+.2f} eq={equity:.0f}")

    for i in range(n):
        b = bars[i]
        e = ema[i]
        _new1h = []
        while _mw1h_ptr < len(_mw1h) and _mw1h[_mw1h_ptr][0] <= b.t:
            _ct, _dh, _p1 = _mw1h[_mw1h_ptr]; _mw1h_ptr += 1
            if _dh == 1: _last1hW = _ct
            else:        _last1hM = _ct
            _new1h.append((_dh, _p1))
        if VT_ON and _vt is not None and _vt[i] > 0:
            _vt_now = max(VT_LO, min(VT_HI, _vtmed / _vt[i]))

        # 1) Stops & TP1 für alle Lots
        for L in lots[:]:
            hit = (L.dir == 1 and b.l <= L.sl) or (L.dir == -1 and b.h >= L.sl)
            if hit:
                close_lot(L, L.sl, b.t, "SL" if not L.partial_done else "BE")
                lots.remove(L); continue
            if not L.partial_done:
                if (L.dir == 1 and b.h >= L.tp1) or (L.dir == -1 and b.l <= L.tp1):
                    take_tp1(L, b.t)
            if BE_R > 0:
                be_hit = (L.dir == 1 and b.h >= L.entry + BE_R*L.risk_pu) or \
                         (L.dir == -1 and b.l <= L.entry - BE_R*L.risk_pu)
                if be_hit:
                    L.sl = max(L.sl, L.entry) if L.dir == 1 else min(L.sl, L.entry)
            if TS_D > 0 and (b.t - L.entry_t) >= TS_D*86400 and L.risk_pu > 0:
                _ur = (b.c - L.entry) * L.dir / L.risk_pu
                if _ur < TS_R:
                    close_lot(L, b.c, b.t, "TimeStop"); lots.remove(L); continue
        if not lots:
            prevM_high = prevW_low = None

        # 2) W/M-Erkennung (v13)
        wev = mev = False; wp1 = mp1sig = None
        if e is not None and i >= PIV:
            ih = is_inv_hammer(b); ha = is_hammer(b)
            _rg=b.h-b.l
            vec = vol_sma[i] > 0 and b.v >= VEC_MULT * vol_sma[i]
            _lwk=(min(b.o,b.c)-b.l)/_rg if _rg>0 else 0.0
            _uwk=(b.h-max(b.o,b.c))/_rg if _rg>0 else 0.0
            ihv = ih or (vec and _uwk>=VEC_WICK)
            hav = ha or (vec and _lwk>=VEC_WICK)
            locHigh = b.h >= max(highs[i - PIV:i]); locLow = b.l <= min(lows[i - PIV:i])
            # M
            if mp1 is None:
                if ihv and locHigh and b.c > e:
                    mp1, mp1bar, mp2bar, m_trough, m_wl = b.h, i, None, b.l, m_wick_limit(b)
            else:
                if b.h > mp1:
                    if ihv and locHigh and b.c > e:
                        mp1, mp1bar, mp2bar, m_trough, m_wl = b.h, i, None, b.l, m_wick_limit(b)
                    else:
                        mp1 = None; mp2bar = None
                elif (i - mp1bar) > MW_MAX:
                    mp1 = None; mp2bar = None
                else:
                    m_trough = min(m_trough, b.l)
                    if mp2bar is None:
                        if (i - mp1bar) >= MW_MIN and b.l <= e * (1 + EMA_TOL):
                            mp2bar = i; m_p2peak = b.c
                    else:
                        fib = m_trough + FIB * (mp1 - m_trough)
                        if (i - mp2bar) >= MW_MIN and ihv and locHigh and b.c > e and b.h <= mp1 \
                                and b.h >= fib and b.h <= m_wl and b.h >= m_p2peak and b.c < mp1:
                            mev, mp1sig = True, mp1; mp1 = None; mp2bar = None
                        m_p2peak = max(m_p2peak, b.c)
            # W
            if wp1v is None:
                if hav and locLow and b.c < e:
                    wp1v, wp1bar, wp2bar, w_peak, w_wl = b.l, i, None, b.h, w_wick_limit(b)
            else:
                if b.l < wp1v:
                    if hav and locLow and b.c < e:
                        wp1v, wp1bar, wp2bar, w_peak, w_wl = b.l, i, None, b.h, w_wick_limit(b)
                    else:
                        wp1v = None; wp2bar = None
                elif (i - wp1bar) > MW_MAX:
                    wp1v = None; wp2bar = None
                else:
                    w_peak = max(w_peak, b.h)
                    if wp2bar is None:
                        if (i - wp1bar) >= MW_MIN and b.h >= e * (1 - EMA_TOL):
                            wp2bar = i; w_p2trough = b.c
                    else:
                        fib = w_peak - FIB * (w_peak - wp1v)
                        if (i - wp2bar) >= MW_MIN and hav and locLow and b.c < e and b.l >= wp1v \
                                and b.l <= fib and b.l >= w_wl and b.l <= w_p2trough and b.c > wp1v:
                            wev, wp1 = True, wp1v; wp1v = None; wp2bar = None
                        w_p2trough = min(w_p2trough, b.c)

        # 2b) BCR PRICE-ACTION (entkoppelt von W/M): Vektor-Break 50EMA -> Lauf 200EMA -> Retest 50EMA + Hammer
        bcrL=False; bcrS=False; bcrL_sl=None; bcrS_sl=None
        wp2_prev=wp2bar; mp2_prev=mp2bar
        if BCR_ON and e is not None:
            e2=ema200[i]
            vecB = vol_sma[i]>0 and b.v>=BCR_VEC*vol_sma[i]
            # ---- LONG: Vektor-Break hoch ----
            if vecB and b.c>e and (b.o<=e or bars[i-1].c<=ema[i-1]):
                cL={'bar':i,'sl':min(lows[max(0,i-BCR_SWLB+1):i+1]),'exp':False}
            if cL is not None:
                if i-cL['bar']>BCR_WIN: cL=None
                elif b.c < cL['sl']: cL=None
                else:
                    if not cL['exp']:
                        if not BCR_200: cL['exp']=True
                        elif e2 is not None:
                            if BCR_200MODE=='since':
                                if max(highs[cL['bar']:i+1])>=e2*(1-BCR_200TOL): cL['exp']=True
                            elif BCR_200MODE=='sinceswap':
                                if min(lows[cL['bar']:i+1])<=e2*(1+BCR_200TOL): cL['exp']=True
                            elif b.h>=e2*(1-BCR_200TOL): cL['exp']=True
                    else:
                        ham=(not BCR_HAM) or is_hammer(b)
                        if (i-cL['bar'])>=BCR_MINRT and b.l<=e*(1+BCR_TOL) and b.c>e and b.l>cL['sl'] and ham:
                            bcrL=True; bcrL_sl=cL['sl']; cL=None
            # ---- SHORT: Vektor-Break runter ----
            if vecB and b.c<e and (b.o>=e or bars[i-1].c>=ema[i-1]):
                cS={'bar':i,'sl':max(highs[max(0,i-BCR_SWLB+1):i+1]),'exp':False}
            if cS is not None:
                if i-cS['bar']>BCR_WIN: cS=None
                elif b.c > cS['sl']: cS=None
                else:
                    if not cS['exp']:
                        if not BCR_200: cS['exp']=True
                        elif e2 is not None:
                            if BCR_200MODE=='since':
                                if min(lows[cS['bar']:i+1])<=e2*(1+BCR_200TOL): cS['exp']=True
                            elif BCR_200MODE=='sinceswap':
                                if max(highs[cS['bar']:i+1])>=e2*(1-BCR_200TOL): cS['exp']=True
                            elif b.l<=e2*(1+BCR_200TOL): cS['exp']=True
                    else:
                        ham=(not BCR_HAM) or is_inv_hammer(b)
                        if (i-cS['bar'])>=BCR_MINRT and b.h>=e*(1-BCR_TOL) and b.c<e and b.h<cS['sl'] and ham:
                            bcrS=True; bcrS_sl=cS['sl']; cS=None

        # 2c) With-Trend Continuation Entry (CTE): Pullback zur 50EMA im Trend
        cteL=False; cteS=False; cteL_sl=None; cteS_sl=None
        if CTE_ON and e is not None and i>=CTE_N:
            _e2=ema200[i]; _spc=(_e2-ema200[i-CTE_N])/_e2
            _upreg = _spc> CTE_TH and e> _e2*(1+CTE_SEP)   # 50EMA ueber 200EMA = Aufwaertstrend
            _dnreg = _spc< -CTE_TH and e< _e2*(1-CTE_SEP)  # 50EMA unter 200EMA = Abwaertstrend
            if _upreg and b.l<=e*(1+CTE_TOL) and b.c>e and is_hammer(b):
                cteL=True; cteL_sl=min(lows[max(0,i-CTE_SWLB+1):i+1])
            if _dnreg and b.h>=e*(1-CTE_TOL) and b.c<e and is_inv_hammer(b):
                cteS=True; cteS_sl=max(highs[max(0,i-CTE_SWLB+1):i+1])

        # 3) Signal-Handling (Pyramiding / Flip)
        if b.t >= win_start:
            sigs=[]
            if MW_ON: sigs += [(1, wev, wp1, 'mw'), (-1, mev, mp1sig, 'mw')]
            if MW1H_SIG:
                for _dh, _p1 in _new1h:
                    sigs.append((_dh, True, _p1, 'mw1h'))
            if BCR_ON:
                _flatok = (not BCR_FLAT) or (len(lots)==0)
                if bcrL and bcrL_sl is not None and _flatok: sigs.append((1, True, bcrL_sl, 'bcr'))
                if bcrS and bcrS_sl is not None and _flatok: sigs.append((-1, True, bcrS_sl, 'bcr'))
            if CTE_ON:
                if cteL and cteL_sl is not None: sigs.append((1, True, cteL_sl, 'cte'))
                if cteS and cteS_sl is not None: sigs.append((-1, True, cteS_sl, 'cte'))
            for d, sig_on, sl_ref, tag in sigs:
                if not sig_on:
                    continue
                _ttag = tag
                _ev = dict(t=b.t, dir=d, tag=tag, px=b.c, sl_ref=sl_ref)
                if MTF_ON and DIAG_T1 and DIAG_T0 <= b.t <= DIAG_T1:
                    _b4d=_ctx['4h']['cyc'][i]; _l4d=_ctx['4h']['level'][i] or 0; _l1d=_ctx['1h']['level'][i] or 0; _d1d=_ctx['1D']['cyc'][i]; _erd=_ctx['4h']['er'][i] or 0.0
                    _erok='ok' if _erd>=ER_MIN else 'LOWER'
                    print(f"  {_u2(b.t)} SIG {'LONG ' if d==1 else 'SHORT'}/{tag} @{b.c:.0f}  4hBias{_b4d:+d} 4hL{_l4d} 1hL{_l1d} 1D{_d1d:+d} ER{_erd:.2f}({_erok})  {'WITH-TREND' if d==_b4d else 'REVERSAL'}  pos={len(lots)}")
                if HTF_ON and bias[i]!=d:
                    _sig_rec(_ev, 'htf'); continue
                if MTF_ON:
                    if CC_BIAS:                           # Bias/Level aus Zyklus-Zähler
                        _b4=_cc_d4[i]; _l4=_cc_l4[i] or 0; _l1=_cc_l1h[i] or 0; _d1=_cc_d1[i]
                    else:
                        _b4   = _ctx['4h']['cyc'][i]      # 4h-Trend (3-Tage-Swing)
                        _l1   = _ctx['1h']['level'][i] or 0
                        _l4   = _ctx['4h']['level'][i] or 0
                        _d1   = _ctx['1D']['cyc'][i]      # 1D-Makro
                    _ev.update(bias4=_b4, l1=_l1, l4=_l4, d1=_d1,
                               er=round((_ctx[ER_TF]['er'][i] or 0), 3))
                    if BIAS_MODE == 'conf':
                        # Bias nur wenn 1D UND 4h übereinstimmen, sonst aussetzen (Konfluenz)
                        if _d1 == 0 or _b4 == 0 or _d1 != _b4:
                            _sig_rec(_ev, 'bias_conf'); continue
                        _bias = _b4
                    else:
                        _bias = _b4
                    if _bias == 0:
                        _sig_rec(_ev, 'bias0'); continue  # kein klarer Bias -> aussetzen
                    _ev['side'] = 'wt' if d == _bias else 'rev'
                    if ER_MIN > 0 and (_ctx[ER_TF]['er'][i] or 0) < ER_MIN:
                        _sig_rec(_ev, 'er_low'); continue # Levels am Bias-TF nicht klar genug -> aussetzen
                    _ttag = tag + ('/wt' if d == _bias else '/rev')
                    if BCR_WT_ONLY and tag == 'bcr' and d != _bias:
                        # Ausnahme (Wookie 23.7.): bcr/rev erlaubt, wenn 1h-M/W gleicher
                        # Richtung binnen BCR_REV_1H Stunden die Trap-Struktur liefert
                        _1h_ok = BCR_REV_1H > 0 and (
                            (d == -1 and b.t - _last1hM <= BCR_REV_1H*3600) or
                            (d == 1 and b.t - _last1hW <= BCR_REV_1H*3600))
                        if not _1h_ok:
                            _sig_rec(_ev, 'bcr_wt_only'); continue  # BCR ist Continuation, kein Reversal-Trigger
                    if d == _bias:
                        # WITH-TREND: nur in fruehem/mittlerem 1h-Level (L1->L2), nicht in L3-Erschoepfung
                        if _l1 >= 3:
                            _sig_rec(_ev, 'wt_l1max'); continue
                        if MTF_MACRO and _d1 != 0 and _d1 != d:
                            _sig_rec(_ev, 'wt_macro'); continue  # 1D-Makro muss mit-tragen
                    else:
                        # COUNTER-TREND REVERSAL: nur an 4h-L3-Erschoepfung + am Roadblock
                        if _l4 < 3:
                            _sig_rec(_ev, 'rev_l4'); continue
                        HOD,LOD,HOW,LOW = _kl[i]; px = b.c
                        _lv_all = [x for x in (HOD,LOD,HOW,LOW) if x]
                        if _lv_all:
                            _ev['rb_dist'] = round(min(abs(px-x)/x for x in _lv_all), 5)
                        if RB_MODE == 'band':
                            # TBD-Verschärfung: Close darf max RB_BAND jenseits des Levels liegen
                            # (Docht-Stop-Hunt ok, aber kein fallendes Messer weit unterm Level)
                            if d == 1:
                                near = (LOW and LOW*(1-RB_BAND) <= px <= LOW*(1+MTF_RBTOL)) or \
                                       (LOD and LOD*(1-RB_BAND) <= px <= LOD*(1+MTF_RBTOL))
                            else:
                                near = (HOW and HOW*(1-MTF_RBTOL) <= px <= HOW*(1+RB_BAND)) or \
                                       (HOD and HOD*(1-MTF_RBTOL) <= px <= HOD*(1+RB_BAND))
                        elif RB_MODE == 'reclaim':
                            # TBD-Snatch-Away: Level in letzten RB_LB Bars per Docht touchiert/durchstochen,
                            # Signalkerze schliesst wieder DIESSEITS (kein Vollkoerper jenseits)
                            _lo = min(lows[max(0,i-RB_LB+1):i+1]); _hi = max(highs[max(0,i-RB_LB+1):i+1])
                            if d == 1:
                                near = (LOW and _lo <= LOW*(1+MTF_RBTOL) and px >= LOW) or \
                                       (LOD and _lo <= LOD*(1+MTF_RBTOL) and px >= LOD)
                            else:
                                near = (HOW and _hi >= HOW*(1-MTF_RBTOL) and px <= HOW) or \
                                       (HOD and _hi >= HOD*(1-MTF_RBTOL) and px <= HOD)
                        else:
                            if d == 1:
                                near = (LOW and px <= LOW*(1+MTF_RBTOL)) or (LOD and px <= LOD*(1+MTF_RBTOL))
                            else:
                                near = (HOW and px >= HOW*(1-MTF_RBTOL)) or (HOD and px >= HOD*(1-MTF_RBTOL))
                        if not near:
                            _sig_rec(_ev, 'rev_roadblock'); continue
                        if REV_VOL > 0 and not (vol_sma[i] > 0 and b.v >= REV_VOL*vol_sma[i]):
                            _sig_rec(_ev, 'rev_vol'); continue  # SVC-Proxy: Reversal braucht Volumen-Spike
                if TDIR_ON:
                    _up=_dn=True
                    if TDIR_MODE=='slope' and i>=TDIR_N:
                        _sl=(ema200[i]-ema200[i-TDIR_N])/ema200[i]
                        _up=_sl> TDIR_TH; _dn=_sl< -TDIR_TH
                    elif TDIR_MODE=='ema800' and _ema800 is not None:
                        _up=ema200[i]>_ema800[i]; _dn=ema200[i]<_ema800[i]
                    elif TDIR_MODE=='stack':
                        _up=ema[i]>ema200[i]; _dn=ema[i]<ema200[i]
                    if (d==1 and not _up) or (d==-1 and not _dn):
                        _sig_rec(_ev, 'tdir'); continue
                if E200_ON and tag!='cte':
                    _rsp=(ema200[i]-ema200[i-CTE_N])/ema200[i] if i>=CTE_N else 0.0
                    _sdn = REGIME_ON and _rsp< -REG_TH and e is not None and e<ema200[i]*(1-REG_SEP)
                    _sup = REGIME_ON and _rsp>  REG_TH and e is not None and e>ema200[i]*(1+REG_SEP)
                    if _sdn:
                        if d==1: continue          # kein Counter-Trend-Long im Abwaertstrend
                    elif _sup:
                        if d==-1: continue          # kein Counter-Trend-Short im Aufwaertstrend
                    else:
                        if (d==-1 and not (b.c>ema200[i])) or (d==1 and not (b.c<ema200[i])):
                            continue
                if SLOPE_ON and tag!='cte' and i>=SLOPE_N:
                    _spc=(ema200[i]-ema200[i-SLOPE_N])/ema200[i]
                    if (d==1 and _spc<-SLOPE_TH) or (d==-1 and _spc>SLOPE_TH):
                        continue
                if lots and lots[0].dir != d:
                    # Gegen-Signal -> alles flippen
                    for L in lots[:]:
                        close_lot(L, b.c, b.t, "Flip")
                    lots.clear()
                    prevM_high = prevW_low = None
                    open_lot(d, b.c, b.t, sl_ref, _ttag)
                    _sig_rec(_ev, 'pass_flip')
                    if d == 1: prevW_low = b.l
                    else:      prevM_high = b.h
                else:
                    # gleiche Richtung (oder flat): trailen + ggf. neuer Lot
                    if d == 1:
                        for L in lots:
                            if prevW_low is not None and prevW_low > L.sl and prevW_low < b.c:
                                L.sl = prevW_low
                        prevW_low = b.l
                    else:
                        for L in lots:
                            if prevM_high is not None and prevM_high < L.sl and prevM_high > b.c:
                                L.sl = prevM_high
                        prevM_high = b.h
                    # Pyramiding (aus im Single-Modus): nur wenn flat einen Lot
                    if (not NOPYR) or (not lots):
                        open_lot(d, b.c, b.t, sl_ref, _ttag)
                        _sig_rec(_ev, 'pass')
                    else:
                        _sig_rec(_ev, 'samedir_trail')

            # EXIT_RAW: rohes Gegensignal schliesst die Position, auch wenn das
            # Entry-Gate (Bias/Level/ER/Roadblock) den Gegen-ENTRY blockt hat.
            if EXIT_RAW != 'off' and lots:
                _d0 = lots[0].dir
                _rawL = wev or (EXIT_RAW == 'all' and bcrL)
                _rawS = mev or (EXIT_RAW == 'all' and bcrS)
                if (_d0 == 1 and _rawS) or (_d0 == -1 and _rawL):
                    for L in lots[:]:
                        close_lot(L, b.c, b.t, "RawFlip")
                    lots.clear()
                    prevM_high = prevW_low = None

        max_conc = max(max_conc, len(lots))
        peak = max(peak, equity); max_dd = max(max_dd, (peak - equity) / peak)

    for L in lots[:]:
        close_lot(L, bars[-1].c, bars[-1].t, "EndOfData")
    return trades, equity, max_dd, max_conc


def report(trades, equity, max_dd, max_conc):
    n = len(trades)
    wins = [t for t in trades if t.r > 0]
    gp = sum(t.r for t in wins); gl = -sum(t.r for t in trades if t.r <= 0)
    pf = (gp / gl) if gl else float("inf")
    tot_r = sum(t.r for t in trades)
    print("=" * 56)
    print(f"  BCRv2  MW={os.environ.get('MW_ON','1')} BCR={os.environ.get('BCR_ON','0')} neck={os.environ.get('BCR_NECK','1')} 200={os.environ.get('BCR_200','0')} ham={os.environ.get('BCR_HAM','1')}")
    print("=" * 56)
    print(f"  Trades (Lots) gesamt : {n}")
    print(f"  Max gleichzeitig offen: {max_conc}")
    print(f"  Endkapital           : {equity:,.0f} USDT  (Start {INIT_CAP:,.0f})")
    print(f"  Netto-Return         : {(equity/INIT_CAP-1)*100:+.2f} %")
    print(f"  Summe R              : {tot_r:+.1f} R")
    if n:
        print(f"  Trefferquote         : {len(wins)/n*100:.2f} %")
        print(f"  Ø R / Trade (Exp.)   : {tot_r/n:+.3f} R")
    print(f"  Profit-Faktor (R)    : {pf:.3f}")
    print(f"  Max. Drawdown        : {max_dd*100:.2f} %")
    print("=" * 56)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Nutzung: python3 wm_sar_backtester_v16.py <ohlcv.csv>")
        sys.exit(1)
    bars = load_csv(sys.argv[1])
    print(f"Geladen: {len(bars)} Bars  ({bars[0].t} .. {bars[-1].t})")
    trades, equity, max_dd, max_conc = run(bars)
    report(trades, equity, max_dd, max_conc)
