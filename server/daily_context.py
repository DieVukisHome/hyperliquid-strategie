#!/usr/bin/env python3
"""
Deterministischer Tages-Kontext für die BTC-Analyse / den KI-Bewerter.

Sammelt ALLES Maschinenlesbare selbst (Engine-Read + orthogonale Marktdaten),
damit das LLM nur noch INTERPRETIERT statt Daten zu beschaffen:
  - Engine: 4h-Bias, Level-Counts (1h/4h/1D), 4h-ER, Position, Signale der
    letzten 48h inkl. Gate-Grund, Key-Levels (HOD/LOD/HOW/LOW) mit Distanz.
  - Markt: Funding (Binance + Hyperliquid), Open Interest (+48h-Änderung),
    Fear&Greed (7 Tage). Jede Quelle fail-soft (None + Fehlernotiz).

Nutzung:
  python3 server/daily_context.py            # JSON nach stdout
  python3 server/daily_context.py --md       # zusätzlich Markdown-Block
  python3 server/daily_context.py --csv backtest/data/BTCUSDT_15m_4y.csv  # Offline-Test
"""
import os, sys, json, argparse, datetime as dt, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

from signal_watcher import CHAMP  # noqa: E402  — dieselbe Config wie der Watcher
for k, v in CHAMP.items():
    os.environ.setdefault(k, v)

import wm_sar_mtf as ENGINE      # noqa: E402
import levels_mtf as LV          # noqa: E402

SYMBOL = os.environ.get('SYMBOL', 'BTCUSDT')
U2 = lambda t: dt.datetime.utcfromtimestamp(t + 7200).strftime('%d.%m %H:%M')


def _get(url, timeout=10):
    req = urllib.request.Request(url, headers={'User-Agent': 'hyper-trading-context'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _post(url, body, timeout=10):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json',
                                          'User-Agent': 'hyper-trading-context'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def engine_context(csv_path):
    bars = ENGINE.load_csv(csv_path)
    trades, eq, dd, mc = ENGINE.run(bars)
    b = bars[-1]
    ctxs = {}
    for tf in ('1D', '4h', '1h'):
        hb, ct = LV.resample(bars, LV.TF_SEC[tf])
        st, cd, lv, *_ = LV.level_state(hb, LV.REV[tf], LV.VEC_MULT)
        er = LV.efficiency_ratio([x.c for x in hb], LV.ER_N)
        ctxs[tf] = dict(cyc=cd[-1], level=lv[-1], er=round(er[-1], 3))
    kl = LV.key_levels(bars)
    HOD, LOD, HOW, LOW = kl[-1]
    keys = {}
    for name, val in (('HOD', HOD), ('LOD', LOD), ('HOW', HOW), ('LOW', LOW)):
        keys[name] = dict(px=round(val, 1), dist_pct=round((b.c - val) / val * 100, 2)) if val else None
    pos = None
    if trades and trades[-1].reason == 'EndOfData':
        t = trades[-1]
        pos = dict(dir='long' if t.dir == 1 else 'short', tag=t.tag,
                   entry=t.entry, entry_t=U2(t.entry_t), open_r=round(t.r, 2))
    sigs48 = [dict(t=U2(s['t']), tag=s['tag'], side=s.get('side'), dir=s['dir'],
                   px=s['px'], gate=s['gate'], er=s.get('er'))
              for s in ENGINE.LAST_SIGNALS if s['t'] >= b.t - 48 * 3600]
    return dict(
        price=b.c, bar_time=U2(b.t),
        bias_4h=ctxs['4h']['cyc'], level_1h=ctxs['1h']['level'], level_4h=ctxs['4h']['level'],
        makro_1d=ctxs['1D']['cyc'], er_4h=ctxs['4h']['er'], er_1h=ctxs['1h']['er'],
        er_gate_ok=ctxs['4h']['er'] >= float(os.environ.get('ER_MIN', '0.20')),
        position=pos, key_levels=keys, signals_48h=sigs48)


def market_context():
    out = {}
    try:
        d = _get(f'https://fapi.binance.com/fapi/v1/premiumIndex?symbol={SYMBOL}')
        out['funding_binance'] = dict(rate=float(d['lastFundingRate']),
                                      next_t=U2(int(d['nextFundingTime']) // 1000))
    except Exception as e:
        out['funding_binance'] = None; out['funding_binance_err'] = str(e)[:120]
    try:
        d = _post('https://api.hyperliquid.xyz/info', {'type': 'metaAndAssetCtxs'})
        uni, ctxs = d[0]['universe'], d[1]
        i = next(j for j, u in enumerate(uni) if u['name'] == 'BTC')
        c = ctxs[i]
        out['hyperliquid'] = dict(funding=float(c['funding']), oi=float(c['openInterest']),
                                  mark=float(c['markPx']))
    except Exception as e:
        out['hyperliquid'] = None; out['hyperliquid_err'] = str(e)[:120]
    try:
        d = _get(f'https://fapi.binance.com/fapi/v1/openInterest?symbol={SYMBOL}')
        oi_now = float(d['openInterest'])
        h = _get(f'https://fapi.binance.com/futures/data/openInterestHist?symbol={SYMBOL}&period=1h&limit=48')
        oi_48 = float(h[0]['sumOpenInterest']) if h else None
        out['open_interest'] = dict(now=oi_now,
                                    chg_48h_pct=round((oi_now / oi_48 - 1) * 100, 2) if oi_48 else None)
    except Exception as e:
        out['open_interest'] = None; out['open_interest_err'] = str(e)[:120]
    try:
        d = _get('https://api.alternative.me/fng/?limit=7')
        out['fear_greed'] = [dict(v=int(x['value']), label=x['value_classification'])
                             for x in d['data']]
    except Exception as e:
        out['fear_greed'] = None; out['fear_greed_err'] = str(e)[:120]
    return out


def to_markdown(ctx):
    e, m = ctx['engine'], ctx['market']
    L = [f"## Tages-Kontext {ctx['date']} (Stand {e['bar_time']} UTC+2, {SYMBOL} {e['price']:,.0f})\n"]
    L.append(f"**Engine:** 4h-Bias {e['bias_4h']:+d} (L{e['level_4h']}), 1h-L{e['level_1h']}, "
             f"1D-Makro {e['makro_1d']:+d}, 4h-ER {e['er_4h']} "
             f"({'Gate offen' if e['er_gate_ok'] else 'ER-GATE ZU'})")
    L.append(f"**Position:** " + (f"{e['position']['dir']} ({e['position']['tag']}) seit "
             f"{e['position']['entry_t']} @{e['position']['entry']:,.0f}, {e['position']['open_r']:+.2f}R"
             if e['position'] else 'flat'))
    kl = ", ".join(f"{k} {v['px']:,.0f} ({v['dist_pct']:+.1f}%)"
                   for k, v in e['key_levels'].items() if v)
    L.append(f"**Key-Levels:** {kl}")
    if e['signals_48h']:
        L.append("**Signale 48h:** " + "; ".join(
            f"{s['t']} {s['tag']}/{s['side'] or '?'} {'L' if s['dir']==1 else 'S'} → {s['gate']}"
            for s in e['signals_48h']))
    fb = m.get('funding_binance'); hl = m.get('hyperliquid'); oi = m.get('open_interest')
    fg = m.get('fear_greed')
    L.append(f"**Funding:** Binance {fb['rate']*100:.4f}%" if fb else "**Funding:** Binance n/a")
    if hl:
        L.append(f"**Hyperliquid:** Funding {hl['funding']*100:.4f}%, OI {hl['oi']:,.0f}, Mark {hl['mark']:,.0f}")
    if oi:
        L.append(f"**OI Binance:** {oi['now']:,.0f} ({oi['chg_48h_pct']:+.1f}% vs 48h)" if oi.get('chg_48h_pct') is not None else f"**OI Binance:** {oi['now']:,.0f}")
    if fg:
        L.append(f"**Fear&Greed:** heute {fg[0]['v']} ({fg[0]['label']}), 7d: " + " ".join(str(x['v']) for x in fg))
    for k in ('funding_binance_err', 'hyperliquid_err', 'open_interest_err', 'fear_greed_err'):
        if m.get(k):
            L.append(f"_Quelle fehlgeschlagen: {k} → {m[k]}_")
    return "\n\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--csv', default=os.path.join(os.environ.get('SERVER_DIR', HERE),
                                                  'data', f'{SYMBOL}_15m_live.csv'))
    ap.add_argument('--md', action='store_true')
    ap.add_argument('--no-market', action='store_true', help='nur Engine-Teil (Offline-Test)')
    a = ap.parse_args()
    ctx = dict(date=dt.date.today().isoformat(),
               engine=engine_context(a.csv),
               market={} if a.no_market else market_context())
    print(json.dumps(ctx, indent=1, ensure_ascii=False))
    if a.md:
        print("\n" + to_markdown(ctx))


if __name__ == '__main__':
    main()
