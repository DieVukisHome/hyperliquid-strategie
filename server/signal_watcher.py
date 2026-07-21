#!/usr/bin/env python3
"""
Live-Signal-Watcher (deterministisch, KEIN Order-Code — beobachtet & protokolliert nur).

- hält 15m-Daten aktuell (Binance Futures public API, inkrementell, CSV-Cache)
- läuft die v21-Champion-Engine (wm_sar_mtf, BCR_WT_ONLY=1) über ein rollendes Fenster
- loggt ALLE Signal-Events (auch gate-geblockte) ins SQLite-Journal (journal.db)
- neue Events -> JSON in queue/ + optionaler Bewerter-Aufruf (evaluator.py, fail-open)
- pflegt Outcomes nach (Engine-R für genommene Trades, Forward-Returns für alle)
- Heartbeat-File pro Zyklus (fuer externen Watchdog)

Nutzung:
  python3 signal_watcher.py --once            # ein Zyklus (Test/cron)
  python3 signal_watcher.py --loop            # Dauerlauf (launchd)
  python3 signal_watcher.py --once --csv backtest/data/BTCUSDT_15m_4y.csv --no-fetch  # Dry-Run offline

Env: SYMBOL (BTCUSDT) | WATCH_LOOKBACK_D (1460) | EVAL_ON (1) | SERVER_DIR | CATCHUP_BARS (8)
"""
import os, sys, csv, json, time, sqlite3, argparse, subprocess, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)

SYMBOL    = os.environ.get('SYMBOL', 'BTCUSDT')
LOOKB_D   = int(os.environ.get('WATCH_LOOKBACK_D', '1460'))
SRV       = os.environ.get('SERVER_DIR', HERE)
DATA_CSV  = os.path.join(SRV, 'data', f'{SYMBOL}_15m_live.csv')
DB_PATH   = os.path.join(SRV, 'journal.db')
QUEUE_DIR = os.path.join(SRV, 'queue')
HEARTBEAT = os.path.join(SRV, 'heartbeat')
EVAL_ON   = os.environ.get('EVAL_ON', '1') == '1'
CATCHUP   = int(os.environ.get('CATCHUP_BARS', '8'))   # wie viele letzte Bars auf neue Events pruefen
BAR_SEC   = 900

# v22-Champion-Config — setdefault, damit env-Overrides (plist) greifen.
# v22 (21.7.26): + BCR_200MODE=since (Break muss zur 200EMA laufen vor Retest, korrekt-seitig)
#                + TS_D=5/TS_R=1.0 (Time-Stop: nach 5 Tagen unter +1R raus)
# Validiert BTC 4J: +460%/PF3.75/DD18%/OOS+63%; ETH +36%/PF2.20; VIRTUAL +22%/PF2.09.
CHAMP = {'MW_ON':'1','BCR_ON':'1','BCR_FLAT':'1','CTE_ON':'0','E200_ON':'0','SLOPE_ON':'0',
         'HTF_ON':'0','REGIME_ON':'0','NOPYR':'1','RO_ON':'0','TDIR_ON':'0','MTF_ON':'1',
         'BIAS_MODE':'h4','MTF_MACRO':'1','MTF_RBTOL':'0.005',
         'REV_1D':'0.066','REV_4H':'0.033','REV_1H':'0.0165',
         'ER_N':'30','ER_MIN':'0.20','VEC_MULT':'99','LV_VEC_MULT':'1.5',
         'RISK':'0.01','MAX_LEV':'10','VT_ON':'0','CC_BIAS':'0','BCR_WT_ONLY':'1',
         'BCR_200':'1','BCR_200TOL':'0.002','BCR_200MODE':'since',
         'TS_D':'5','TS_R':'1.0'}
for k, v in CHAMP.items():
    os.environ.setdefault(k, v)

import wm_sar_mtf as ENGINE  # noqa: E402


# ---------------- Daten ----------------
def fetch_klines(symbol, start_ms, end_ms=None):
    """Binance Futures 15m-Klines ab start_ms (inkl.), paginiert."""
    out = []
    url_base = 'https://fapi.binance.com/fapi/v1/klines'
    while True:
        url = f'{url_base}?symbol={symbol}&interval=15m&limit=1500&startTime={start_ms}'
        if end_ms:
            url += f'&endTime={end_ms}'
        req = urllib.request.Request(url, headers={'User-Agent': 'hyper-trading-watcher'})
        with urllib.request.urlopen(req, timeout=30) as r:
            batch = json.loads(r.read())
        if not batch:
            break
        out.extend(batch)
        if len(batch) < 1500:
            break
        start_ms = batch[-1][0] + 1
        time.sleep(0.3)
    return out


def update_csv(path):
    """CSV inkrementell aktualisieren; nur GESCHLOSSENE Bars schreiben."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    last_t = None
    if os.path.exists(path):
        with open(path, 'rb') as f:
            try:
                f.seek(-200, 2)
            except OSError:
                f.seek(0)
            tail = f.read().decode().strip().splitlines()
            if tail and not tail[-1].startswith('time'):
                last_t = int(float(tail[-1].split(',')[0]))
    now = int(time.time())
    start = ((last_t + BAR_SEC) if last_t else (now - LOOKB_D * 86400)) * 1000
    rows = fetch_klines(SYMBOL, start)
    closed = [k for k in rows if (k[0] // 1000) + BAR_SEC <= now]
    if not closed:
        return 0
    new_file = not os.path.exists(path)
    with open(path, 'a', newline='') as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(['time', 'open', 'high', 'low', 'close', 'volume'])
        for k in closed:
            w.writerow([k[0] // 1000, k[1], k[2], k[3], k[4], k[5]])
    return len(closed)


# ---------------- Journal ----------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS signals(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  t INTEGER, dir INTEGER, tag TEXT, gate TEXT, side TEXT,
  px REAL, sl_ref REAL, ctx TEXT, created_at INTEGER,
  UNIQUE(t, dir, tag));
CREATE TABLE IF NOT EXISTS verdicts(
  signal_id INTEGER, evaluator TEXT, score REAL, veto INTEGER,
  size_factor REAL, confidence TEXT, reasoning TEXT, raw TEXT, created_at INTEGER,
  UNIQUE(signal_id, evaluator));
CREATE TABLE IF NOT EXISTS outcomes(
  signal_id INTEGER PRIMARY KEY, engine_r REAL, exit_t INTEGER, exit_reason TEXT,
  fwd24 REAL, fwd72 REAL, fwd168 REAL, r24 REAL, r72 REAL, r168 REAL, updated_at INTEGER);
"""


def db():
    os.makedirs(os.path.dirname(DB_PATH) or '.', exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)
    return con


def record_signals(con, sigs, last_t):
    """Alle Events der letzten CATCHUP Bars einfuegen; neue Events zurueckgeben."""
    cutoff = last_t - CATCHUP * BAR_SEC
    new = []
    for s in sigs:
        if s['t'] < cutoff:
            continue
        ctx = {k: v for k, v in s.items()
               if k not in ('t', 'dir', 'tag', 'gate', 'side', 'px', 'sl_ref')}
        cur = con.execute(
            "INSERT OR IGNORE INTO signals(t,dir,tag,gate,side,px,sl_ref,ctx,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (s['t'], s['dir'], s['tag'], s['gate'], s.get('side'),
             s['px'], s.get('sl_ref'), json.dumps(ctx), int(time.time())))
        if cur.rowcount:
            s['signal_id'] = cur.lastrowid
            new.append(s)
    con.commit()
    return new


def update_outcomes(con, bars, trades):
    """Engine-R fuer genommene Trades + Forward-Returns fuer alle Signale nachpflegen."""
    tmap = {}
    for t in trades:
        tmap.setdefault(t.entry_t, t)
    times = [b.t for b in bars]
    import bisect
    now_t = bars[-1].t
    rows = con.execute(
        "SELECT id,t,dir,px,sl_ref,gate FROM signals WHERE id NOT IN "
        "(SELECT signal_id FROM outcomes WHERE r168 IS NOT NULL AND "
        " (exit_t IS NOT NULL OR engine_r IS NULL))").fetchall()
    for sid, st, sdir, spx, ssl, gate in rows:
        vals = dict(engine_r=None, exit_t=None, exit_reason=None,
                    fwd24=None, fwd72=None, fwd168=None, r24=None, r72=None, r168=None)
        tr = tmap.get(st)
        if tr is not None and tr.exit_t:
            vals['engine_r'] = tr.r; vals['exit_t'] = tr.exit_t; vals['exit_reason'] = tr.reason
        risk = abs(spx - ssl) / spx if (ssl and spx) else None
        for h, fk, rk in ((24, 'fwd24', 'r24'), (72, 'fwd72', 'r72'), (168, 'fwd168', 'r168')):
            tt = st + h * 3600
            if tt > now_t:
                continue
            j = bisect.bisect_right(times, tt) - 1
            if j < 0:
                continue
            mv = (bars[j].c - spx) / spx * sdir
            vals[fk] = round(mv, 5)
            if risk:
                vals[rk] = round(mv / risk, 2)
        con.execute(
            "INSERT INTO outcomes(signal_id,engine_r,exit_t,exit_reason,fwd24,fwd72,fwd168,"
            "r24,r72,r168,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(signal_id) DO UPDATE SET engine_r=excluded.engine_r,"
            "exit_t=excluded.exit_t,exit_reason=excluded.exit_reason,fwd24=excluded.fwd24,"
            "fwd72=excluded.fwd72,fwd168=excluded.fwd168,r24=excluded.r24,r72=excluded.r72,"
            "r168=excluded.r168,updated_at=excluded.updated_at",
            (sid, vals['engine_r'], vals['exit_t'], vals['exit_reason'], vals['fwd24'],
             vals['fwd72'], vals['fwd168'], vals['r24'], vals['r72'], vals['r168'],
             int(time.time())))
    con.commit()


# ---------------- Zyklus ----------------
ENGINE_ENVS = sorted(set(list(CHAMP) + ['BCR_200', 'BCR_200TOL', 'BCR_200MODE', 'RB_MODE',
                                        'RB_BAND', 'RB_LB', 'REV_VOL', 'BE_R', 'EXIT_RAW',
                                        'TS_D', 'TS_R', 'ER_TF', 'TP1_R', 'TP1_FRAC']))


def config_guard():
    """Aktive Engine-Config festhalten; bei Abweichung zum letzten Lauf LAUT warnen.
    Verhindert stille Config-Drift: Journal-Daten sind nur innerhalb EINER Config vergleichbar."""
    cfg = {k: os.environ.get(k) for k in ENGINE_ENVS}
    os.makedirs(SRV, exist_ok=True)
    p = os.path.join(SRV, 'active_config.json')
    prev = None
    if os.path.exists(p):
        try:
            prev = json.load(open(p))
        except ValueError:
            pass
    if prev is not None and prev != cfg:
        diff = {k: (prev.get(k), cfg.get(k)) for k in cfg if prev.get(k) != cfg.get(k)}
        print(f"[watcher] *** WARNUNG: ENGINE-CONFIG GEÄNDERT: {diff} ***")
        print("[watcher] *** Journal mischt jetzt zwei Signal-Populationen — Kalibrierung neu starten oder Config zurücksetzen! ***")
    json.dump(cfg, open(p, 'w'), indent=1)


def cycle(csv_path, no_fetch=False):
    config_guard()
    if not no_fetch:
        n = update_csv(csv_path)
        print(f"[watcher] {n} neue Bars")
    bars = ENGINE.load_csv(csv_path)
    if len(bars) < 5000:
        print(f"[watcher] WARNUNG: nur {len(bars)} Bars — Kontext evtl. unreif")
    trades, eq, dd, mc = ENGINE.run(bars)
    con = db()
    new = record_signals(con, ENGINE.LAST_SIGNALS, bars[-1].t)
    update_outcomes(con, bars, trades)
    os.makedirs(QUEUE_DIR, exist_ok=True)
    for s in new:
        print(f"[watcher] NEUES EVENT: {s['gate']} {s['tag']}/{s.get('side','?')} "
              f"dir={s['dir']} @{s['px']}")
        ev_path = os.path.join(QUEUE_DIR, f"{s['t']}_{s['tag']}_{s['dir']}.json")
        with open(ev_path, 'w') as f:
            json.dump(s, f, indent=1)
        if EVAL_ON:
            try:
                subprocess.run([sys.executable, os.path.join(HERE, 'evaluator.py'), ev_path],
                               timeout=600)
            except Exception as e:   # fail-open: Bewerter-Fehler blockiert nie den Watcher
                print(f"[watcher] Evaluator-Fehler (fail-open): {e}")
    with open(HEARTBEAT, 'w') as f:
        f.write(str(int(time.time())))
    con.close()
    return len(new)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--once', action='store_true')
    ap.add_argument('--loop', action='store_true')
    ap.add_argument('--csv', default=DATA_CSV)
    ap.add_argument('--no-fetch', action='store_true')
    a = ap.parse_args()
    if a.once or not a.loop:
        cycle(a.csv, a.no_fetch)
        return
    while True:
        try:
            cycle(a.csv, a.no_fetch)
        except Exception as e:
            print(f"[watcher] Zyklus-Fehler: {e}")
        now = time.time()
        nxt = (int(now // BAR_SEC) + 1) * BAR_SEC + 20   # 20s nach Bar-Close
        time.sleep(max(30, nxt - now))


if __name__ == '__main__':
    main()
