# Pine v22 (TradingView) ↔ Python-Engine Divergenzen

Wenn TV-Chart Marker zeigt die im Python-Journal fehlen (oder umgekehrt):
**Journal + `ENGINE.LAST_SIGNALS` sind autoritativ für das was wirklich getradet würde.**
Pine v22 auf TV ist Visualisierung, kann abweichen.

## Vorfall-Log

| Datum | User-Beobachtung TV | Journal / LAST_SIGNALS | Diagnose |
|---|---|---|---|
| **2026-08-13** | 03:45+05:15+05:30 gab's 3 Signale in Telegram, aber TV zeigte nur 05:30 (mw/rev L) | id=337 `bcr/bcr_wt_only` S (blockiert), id=344 `bcr/pass` L (getradet), id=347 `mw/rev_l4` S (blockiert) — alle drei detektiert | Pine plotet `bcrL`/`bcrS` (**Rohsignal**, unabhängig vom Gate). Wenn Pine's Detector nichts sieht wo Python's schon: Symbol- oder Params-Drift vermutet |
| **2026-08-18 10:00 CEST** | `L WT` grünes Entry-Label im TV | Python `LAST_SIGNALS`: `mw/wt dir=+1 @64130.4`, aber **`gate=er_low`** (4h-ER unter 0.20 → geblockt) | ⚠️ **Erst-Diagnose war FALSCH** ("Pine plotet vor dem ER-Filter") — das `L WT`-Label haengt in v22 sehr wohl an `f_gate()` inkl. ER-Check. **Echte Ursache: HTF-Intrabar-Lesen (siehe unten), in v23 gefixt.** |
| **2026-08-19 ~14:00 CEST** | BCR-LONG Marker auf TV | 0 Signale in letzten 8h in Journal + LAST_SIGNALS leer | Nach Nachfragen stellte sich raus: User hatte Datum verwechselt, war der 18.08-Fall (siehe oben) |

## GELÖST in Pine v23 (19.8.2026) — zwei systematische Ursachen

Beide Divergenzen waren ECHTE Pine-Bugs (nicht "Rohsignal vs Gate"):

**(1) HTF-Kontext wurde intrabar gelesen.** v22 holte Bias/Level/ER mit
`request.security(..., f_struct(...), lookahead_off)` **ohne `[1]`** → das liefert den
LAUFENDEN, noch offenen HTF-Bar; der Wert aendert sich waehrend der 4h-Bar entsteht.
Python (`map_to_15m()`) nutzt dagegen immer den letzten **GESCHLOSSENEN** HTF-Bar.
Pine lief dem Python damit bis zu 4 Stunden voraus.
**Quantifiziert ueber 4 Jahre BTC 15m (144.788 Bars): 9,2% aller Bars hatten eine
ANDERE ER-Gate-Entscheidung** (6.675× Pine offen/Python zu — genau der 18.08-Fall;
6.617× umgekehrt). Betrifft gleichermassen `d4h`/`l1h`/`l4h`/`d1d`, also auch Bias-,
Level- und Makro-Gate.
Fix v23: `f_struct_conf()` / `f_er_conf()` geben `[1]` zurueck, Aufruf mit
`lookahead=barmerge.lookahead_on` (Standard-Non-Repaint-Idiom, kein Future-Leak da
der VORHERIGE, abgeschlossene HTF-Bar gelesen wird).

**(2) Key-Levels lagen auf der falschen Tages-/Wochengrenze.** v22 nutzte
`request.security(..., "D"/"W", high[1]/low[1])` — bei Krypto auf TV ist das die
**UTC**-Session. Python `key_levels()` ankert aber **17:00 New York** (Woche: So 17:00).
HOD/LOD/HOW/LOW waren also verschoben → das Roadblock-Gate (`rev_roadblock`) konnte
in Pine und Python unterschiedlich urteilen.
Fix v23: manuelle Verankerung via `hour(time,"America/New_York")==17`-Reset
(`f_prevExtremes()`), plus die vier Levels sind jetzt als Linien geplottet.

**Konsequenz:** Ab v23 sollten Pine-Entry-Labels und Journal-`pass`-Signale
uebereinstimmen. Bleibt eine Abweichung, ist es ein NEUER Fall → unten eintragen.
Der Strategy-Tester zeigt ab v23 andere (korrektere) Zahlen als v22 — erwartet.

## Standardvorgehen bei "TV zeigt X, Python zeigt Y"

1. **User nach exaktem Datum + Uhrzeit fragen** — auf TV auf die fragliche Bar tippen, unten steht "Di 18 Aug '26 10:00" oder ähnlich. Auch O/H/L/C-Werte der Cursor-Bar notieren lassen. **Datum-Verwechslung ist häufig.**
2. **`LAST_SIGNALS` + Journal für den Zeitraum abfragen** (Snippet unten).
3. **Bar-Werte O/H/L/C gegen CSV vergleichen** — identisch → kein Feed-Drift, Divergenz liegt im Detector oder Gate.
4. **Klassifikation:**
   - Python hat + Gate `pass|pass_flip|samedir_trail` → sollte in TV auch Marker haben. Wenn nicht → Symbol/Version/Params im TV falsch (siehe Diagnose-Checkliste unten).
   - **Python hat + Gate blockiert (`er_low`, `bcr_wt_only`, `wt_macro`, `rev_l4`, `bias0`, `bias_conf`, `wt_l1max`) → Pine zeigt Rohsignal oder hätte-Entry, Engine tradet nicht — konsistent, kein Bug.**
   - Python hat NICHT → Pine irrt oder Config drift. Diagnose-Checkliste durchgehen.

## Diagnose-Checkliste bei "Python hat NICHT"

1. **Chart-Symbol im TV**: Spot `BINANCE:BTCUSDT` vs Perp `BINANCE:BTCUSDT.P`? Python-Engine holt Binance Futures/Perp (`fapi.binance.com`, `BTCUSDT`). Wenn TV auf Spot → andere Kerzen → andere Trigger.
2. **Pine-Version im Chart-Header**: `TBD W/M SAR v23 Champion` (Slot "TBD Method Codex Fork v21", ab Version 86)? v22 und aelter lesen HTF intrabar + falscher Key-Level-Anker (siehe oben) → systematische Abweichung. v20/v21 haben KEIN `bcr200On`-Latch → BCR feuert bei Break ohne 200-EMA-Reach → mehr Marker. v21 hatte kein `bcrWtOnly` → mehr Reversal-BCRs.
3. **BCR-Input-Werte im Pine-Settings-Panel** (müssen zu `active_config.json` / CHAMP passen):
   - `bcrWin = 120` · `bcrTol = 0.0015` · `bcr200Tol = 0.002` · `bcrVec = 1.5` · `bcr200On = true` · `bcrWtOnly = true`
4. **Struktur-Params**: `Rev1D = 0.066` · `Rev4H = 0.033` · `Rev1H = 0.0165` · `ER_N = 30` · `ER_MIN = 0.2`
5. **Bar-Confirm**: Pine kann bei OFFENER Kerze Marker anzeigen; Python wartet auf close.

## Query-Snippet (Direkt-Check `LAST_SIGNALS` + Journal)

```python
import os, sys, time, sqlite3, datetime
sys.path.insert(0, '/Users/Vuki/hyperliquid-strategie')
sys.path.insert(0, '/Users/Vuki/hyperliquid-strategie/server')
from signal_watcher import CHAMP
for k, v in CHAMP.items(): os.environ.setdefault(k, v)
import wm_sar_mtf as ENGINE

bars = ENGINE.load_csv('/Users/Vuki/hyperliquid-strategie/server/data/BTCUSDT_15m_live.csv')
trades, *_ = ENGINE.run(bars)
now = int(time.time())
# LAST_SIGNALS für letzte 24h
recent = [s for s in ENGINE.LAST_SIGNALS if s['t'] >= now - 86400]
for s in recent:
    t = datetime.datetime.utcfromtimestamp(s['t']+7200).strftime('%m-%d %H:%M UTC+2')
    print(f"{t} {s['tag']}/{s.get('side','?')} dir={s['dir']:+} @{s['px']} → gate={s['gate']}")

# Journal für letzte 24h (nur wirklich persistierte)
c = sqlite3.connect('/Users/Vuki/hyperliquid-strategie/server/journal.db')
for r in c.execute('SELECT id,t,tag,gate,dir,px FROM signals WHERE t > ? ORDER BY t', (now-86400,)):
    print(f"  DB: id={r[0]} {datetime.datetime.utcfromtimestamp(r[1]+7200).strftime('%m-%d %H:%M UTC+2')} {r[2]}/{r[3]} dir={r[4]:+} @{r[5]}")
```

## Live-Trading-Grundregel

Trades laufen ausschließlich über die Python-Engine (`signal_watcher.py` + `evaluator.py`).
Pine v22 auf TV ist **zum Mitlesen für den User**, nicht Ausführung. Wenn TV-Marker fehlt,
den die Engine getradet hätte: Journal ist Wahrheit, TV irrt. Wenn TV-Marker existiert,
den die Engine NICHT tradet: fast immer gate-blocked (siehe LAST_SIGNALS `gate`-Feld).
