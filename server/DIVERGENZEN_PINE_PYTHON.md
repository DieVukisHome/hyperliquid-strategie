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

### Nachrechnung am 18.08-Fall (19.8., frische Kerzen bis 19.08 22:15)

`server/pine_parity_check.py 2026-08-18T10:00` liefert:

```
18.08 10:00 mw/wt dir=+1 @64130.4 -> gate=er_low   (bias4=1 l1=0 l4=2 d1=1 er=0.082)
10:00  v23/Python 0.082 ZU | v22-alt 0.177 ZU    *SIGNAL*
10:30  v23/Python 0.082 ZU | v22-alt 0.209 OFFEN  <-- Divergenz
10:45  v23/Python 0.082 ZU | v22-alt 0.210 OFFEN  <-- Divergenz
```

### AUFGELÖST (19.8. abends, per Chart-Screenshot)

Der Chart zeigt `Bitcoin / TetherUS PERPETUAL CONTRACT · 15 · Binance` → **Symbol korrekt**,
Spot-Hypothese erledigt. Und der entscheidende Punkt: das grüne **`W` ist KEIN Entry-Label,
sondern der ROH-Signal-Marker** `plotshape(wSig, "W", ...)` — er feuert per Design
unabhängig vom Gate. Dasselbe gilt für die `B`-Dreiecke (BCR roh).

Python hatte an derselben Bar **dasselbe** Roh-Signal: `18.08 10:00 mw/wt dir=+1 @64130.4,
gate=er_low (er=0.082)`. **Also volle Übereinstimmung — es gab nie eine Divergenz.**
Die Verwechslung war: Roh-Marker (`W`, `M`, `B`) vs Entry-Label (`L WT` / `S REV L3`).

**Merkregel für den Chart:**
| Marker | Bedeutung | Engine tradet? |
|---|---|---|
| grünes `W` / rotes `M` | M/W-Formation erkannt (roh, ungated) | nur wenn zusätzlich Entry-Label |
| `B`-Dreieck (aqua/magenta) | BCR-Retest erkannt (roh, ungated) | dito |
| **`L WT` / `L REV Lx` / `S ...`** | **Gate bestanden → Entry** | **ja** |
| `Lx` / `Sx` + Prozentzahl | TradingView-Strategy-Exit | — |

**Historischer Zwischenstand (Analyse-Weg, bewusst erhalten):** Am Signal-Bar 10:00 blocken BEIDE Semantiken
(0.082 bzw. 0.177, beide < 0.20). Die HTF-Semantik erklaert ein `L WT`-Label um
**10:00 also NICHT**. Sie erklaert es erst ab **10:30/10:45** (v22-alt OFFEN) — dort
gibt es aber gar kein M/W-Rohsignal. Fuer das beobachtete Label bleiben damit offen:

1. **Chart-Symbol**: `BINANCE:BTCUSDT.P` (Perp) vs Spot `BINANCE:BTCUSDT` —
   andere Kerzen, anderer 50-EMA-Touch, andere M/W-Detektion. **Haeufigste Ursache.**
2. **Pine-Version im Chart** war evtl. aelter als v22.
3. Uhrzeit-/Datums-Verwechslung (auf TV die Bar antippen, Zeitstempel notieren).

**Konsequenz:** Ab v23 sollten Pine-Entry-Labels und Journal-`pass`-Signale
uebereinstimmen. Bleibt eine Abweichung, ist es ein NEUER Fall → unten eintragen.
Der Strategy-Tester zeigt ab v23 andere (korrektere) Zahlen als v22 — erwartet.

## ROOT CAUSE der ECHTEN Detektor-Divergenz (19.8. — Vektor-Fenster)

Wookies eigentlicher Punkt war nicht das Gate, sondern: **Pine erkennt andere
ROH-Signale als die Engine.** Konkret gemeldet:
- Python: Roh-BCR-Long **18.08 22:00 @64.624,9** (wurde getradet, offen +5,97R) — auf TV **kein** Marker.
- TV: BCR-Long **19.08 14:00** (dort Pines offener Trade) — im Python-Journal **kein** Signal.

**Ursache: unterschiedliches Volumen-Mittelungsfenster für die Vektorkerze.**

| | Fenster für `vol_sma` |
|---|---|
| Python (`wm_sar_mtf.py:288`, `levels_mtf.py:117`) | `bars[i-10 : i]` → die **10 Kerzen VOR** der aktuellen |
| Pine v22/v23 (`ta.sma(volume,10)`) | Kerzen `i-9 .. i` → **inkl. der aktuellen** |

Auf einer Vektorkerze ist das Volumen per Definition hoch — Pine mittelt diesen Spike
mit hinein, die Schwelle `vol >= 1.5×SMA` steigt, das Signal faellt aus.
**Python ist methodisch korrekt** (PVSRA/TBD: *"a 200% increase of the average of the
PRIOR 10 candles to that one"*), Pine war falsch.

**Quantifiziert (4J BTC 15m, Roh-BCR ohne Gate):** Python 2039 · Pine 1893 —
1867 identisch, **172 nur Python**, 26 nur Pine (~8% Divergenz).

**Warum daraus zwei verschiedene offene Trades wurden (Kettenreaktion):**
1. 18.08 22:00 feuert nur bei Python → Engine geht long.
2. `BCR_FLAT=1` (BCR nur wenn flat) unterdrueckt daraufhin bei Python den Roh-BCR vom
   **19.08 14:00 — den Python ebenfalls erkennt** (Detektor-Ebene identisch!), er
   erreicht nur nie das Gate und steht deshalb nicht im Journal.
3. Pine hatte den 18.08-Trade nicht, war flat → nahm 19.08 14:00.

Eine Ursache, beide Beobachtungen. **Fix: Pine v24** — `ta.sma(volume, 10)[1]` an beiden
Stellen (Struktur-Level in `f_struct` + BCR `vsma10`). Python bleibt UNVERAENDERT
(es war korrekt) → keine Neu-Validierung der Engine noetig.

**Lehre fuer kuenftige Ports:** `ta.sma(x, n)` in Pine ist *inklusive* aktueller Bar;
Python-Slices `[i-n:i]` sind *exklusiv*. Bei jeder Schwellenwert-Logik (Vektor, Volumen,
Ranges) explizit pruefen — der Unterschied ist genau dort am groessten, wo der aktuelle
Bar den Ausreisser darstellt, also genau am Signal.

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

## Werkzeug: `server/pine_parity_check.py` (ab 19.8., ERSTE Anlaufstelle)

```bash
python3 server/pine_parity_check.py 2026-08-18T10:00            # Zeit in UTC+2
python3 server/pine_parity_check.py 2026-08-18T10:00 --window 4 # groesseres Fenster
```

Gibt aus: Roh-Signale + Gate-Grund + Kontext im Fenster, ER unter BEIDEN Semantiken
(v23/Python vs v22-alt) und einen Befund-Block mit der naechsten Verdaechtigen-Liste.
Erst wenn das Tool "beide Semantiken blocken identisch" meldet, die Checkliste unten
durchgehen (Symbol/Version/Inputs).

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
