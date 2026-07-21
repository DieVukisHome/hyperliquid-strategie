# Hyper Trading — TBD/Hyperliquid Strategie (Server-Repo)

Dieses Repo enthält den **deterministischen Kern** einer TBD-basierten Trading-Strategie
für die **Hyperliquid** DEX (Perpetuals). Es läuft auf einem always-on Server (Claude Code
im Terminal) und dient als ausführbare Spezifikation + Backtest/Validierung.

## Kurzüberblick

Die Strategie ist ein **W/M-SAR-Reversal-System** mit einem **Multi-Timeframe-Level-Filter**
und einem **Clarity-Filter** (Efficiency Ratio). Über 4 Jahre BTC validiert:
**+328% / Max-DD 27% / OOS +60% / PF ~2.9** (Einzelposition, SAR-Runner). Schlägt die alte
EMA-Filter-Baseline (+71%/4J) in- und out-of-sample.

**Live-Markt = Hyperliquid-Perp.** Backtest-Daten = Binance **Futures/Perp** (NICHT Spot!).
Spot und Perp weichen minimal ab und erzeugen an der Grenze andere Signale — für Vergleiche
immer das Perp-Symbol nutzen.

## Champion-Config (validiert)

```
MTF_ON=1  BCR_ON=1  BCR_FLAT=1  BIAS_MODE=h4  NOPYR=1 (Einzelposition)
BCR_WT_ONLY=1                                 # v21 (14.7.26): BCR nur with-trend, nie als Reversal
BCR_200=1  BCR_200TOL=0.002  BCR_200MODE=since # v22 (21.7.26): Break muss zur 200EMA laufen vor Retest (Wookie-Regel)
TS_D=5  TS_R=1.0                               # v22: Time-Stop — nach 5 Tagen unter +1R raus (Plateau 4-7d, cross-coin+)
REV_1D=0.066  REV_4H=0.033  REV_1H=0.0165     # ZigZag rev% pro TF (Marktstruktur/BoS)
ER_N=30  ER_MIN=0.20                          # Efficiency-Ratio-Clarity-Filter auf 4h
VEC_MULT=99 (M/W-Vektor-P1/P3 AUS)  LV_VEC_MULT=1.5 (Level-Vektor)
MTF_MACRO=1  MTF_RBTOL=0.005                  # 1D-Makro-Gate; Roadblock-Toleranz 0,5%
RISK=0.01  MAX_LEV=10                          # 1% Risiko/Trade; optional VT_ON (Vol-Targeting 0.3-1.0)
```

Gate-Logik: Bias = 4h-BoS-Trend. **With-Trend** wenn 1h-Level<3 (+1D-Makro-Zustimmung);
**Reversal** (Counter-Trend) nur an 4h-Level-3 + Roadblock (HOW/LOW/HOD/LOD ±0,5%),
und NUR per M/W-Formation (BCR_WT_ONLY=1: BCR ist Continuation-Pattern, kein Reversal-Trigger);
Entry nur wenn 4h-ER ≥ 0,20 (Clarity). Exit = reiner SAR-Runner (kein TP), Flip aufs Gegensignal.

**v22-Befund (21.7.26):** BTC 4J **+460%/PF3.75/DD18%/WR21%/OOS+63%**; ETH 1J +36%/PF2.20; VIRTUAL +22%/PF2.09
(alle drei ≥ v21). Bausteine: (a) BCR_200MODE=since — Wookies Regel „Break muss erst zur 200EMA laufen,
sonst Retest ungültig" (blockt Sofort-Signale nach Break; korrekt-seitig: Long max(highs)≥e200, Short min(lows)≤e200!
Server-Bug 14.-21.7. hatte die Seiten vertauscht); (b) TS_D=5/TS_R=1.0 Time-Stop (Plateau 4-7d, beide TS_R,
cross-coin überall besser — erste Exit-Änderung die je alle Tests bestand; 2-3d fallen OOS durch, nicht enger stellen).
GETESTET & NICHT übernommen: BCR_MINRT (min. Bars Break→Retest): BTC stark (OOS+71-73) aber ETH/VIRTUAL schlechter
→ geparkt bis 4J-Alt-Daten. Param-Ensemble (5 Cfg à 1/5 Risiko): DD 21→16.4%/OOS+74 — Option für Executor-Phase.

**v21-Befund (14.7.26, Trade-Tagging wt/rev):** bcr/rev war das Leck (N31, −24R, PF0.14);
mw/rev ist der stärkste Block (PF>6). Mit BCR_WT_ONLY=1: **+408% / DD21% / OOS +62% (PF3.44)**
statt +328/DD27/OOS+60. Robust in allen Param-Nachbarschaften (REV_4H 0.030/0.036, ER 0.17/0.24:
8/8 besser, entschärft die REV_4H-Klippe), ETH 1J neutral, VIRTUAL 1J leicht schwächer (N=5-Rauschen).
Roadblock-Verschärfung (RB_MODE band/reclaim) + SVC-Volumen-Gate (REV_VOL) getestet → fallen OOS durch, AUS lassen.

## Dateien

- `wm_sar_mtf.py` — die **Champion-Engine** (Backtester). Alle Parameter via Umgebungsvariablen.
- `levels_mtf.py` — Multi-TF Level/Struktur-Engine (BoS-Trend, Level-State, Efficiency Ratio, Key-Levels). Wird von wm_sar_mtf importiert.
- `cycle_counter.py` — TBD-Zyklus-Zähler (KONTEXT-Tool, KEIN Trade-Trigger; mechanisiert nicht in Edge, dient nur als grobe Zyklus-Anzeige).
- `run_mtf_compare.py` — Vergleich Champion vs Baseline (4J + IS/OOS-Split).
- `wm_sar_mtf_walkforward.py` — Walk-Forward über die Level-Detektions-Params.
- `TBD_WM_SAR_v20_champion.pine` — Pine-`strategy()`-Port (TradingView), Einzelposition, mit Markern.
- `backtest/fetch_binance_data.py` — Daten holen (Binance public Futures-API, kein Key).
- `server/` — Live-Signal-Watcher + asymmetrischer KI-Bewerter (Shadow-Modus), siehe server/README.md.
  Engine loggt jetzt ALLE Signal-Events inkl. Gate-Grund in `wm_sar_mtf.LAST_SIGNALS` (~1-2/Tag).

## Setup / Backtest

```bash
pip install --break-system-packages   # nur stdlib nötig, keine externen Pakete
# Daten holen (Binance Futures/Perp):
python3 backtest/fetch_binance_data.py --interval 15m --days 1460 --out backtest/data/BTCUSDT_15m_4y.csv
# Champion vs Baseline:
python3 run_mtf_compare.py
```
Die CSVs (`backtest/data/*.csv`) sind absichtlich **nicht** im Repo (groß) — via fetch holen.

## Rolle des Servers + Leitplanken

1. **Deterministischer Kern bleibt schlank.** Der validierte Edge steckt in wm_sar_mtf/levels_mtf.
   Nicht durch diskretionäre/ML-Layer „verbessern" — das overfittet auf ~100-150 Trades/Jahr.
2. **Zyklus-Lesen ≠ Trade-Trigger.** Die exakte TBD-Zyklus-Zählung mechanisiert sich nicht
   (getestet: als Bias −53% vs Champion +328%). cycle_counter nur als Anzeige.
3. **KI-Bewerter (falls gebaut): asymmetrisch + erst nur loggen.** Eine KI-Schicht darf mit
   orthogonalen Daten (Liq-Heatmaps, Funding, OI, Fear&Greed, News) Setups BEWERTEN und Risiko
   SENKEN (Veto/kleiner sizen) — NIE einen Trade eröffnen, den die Engine nicht signalisiert.
   Erst wochenlang mitloggen + gegen Outcomes prüfen, bevor sie echte Trades beeinflusst.
   Der Trade-Trigger bleibt immer deterministisch/auditierbar.
4. **Backtest ≠ Live.** Backtest ohne Funding/Slippage. Hyperliquid-Funding auf tagelange Runner
   ist real → Netto-Return niedriger als Backtest. Beim Deployen abgleichen.
5. **Finanz-Sicherheit:** Trades/Transfers immer nur nach expliziter Freigabe des Users ausführen.

## Offene Punkte (Stand Jul 2026)

- **Cross-coin** (ETH/VIRTUAL) — wichtigster Robustheitstest, bisher alles BTC.
- **Funding/Slippage** modellieren für realistische Netto-Zahlen.
- Formaler Walk-Forward: ~~ER_MIN~~ ERLEDIGT 14.7. (wm_sar_wf_ermin.py): fix 0.20 (+51R)
  schlägt adaptive IS-Wahl (+40R), rho IS→OOS negativ → Wert fixiert lassen, NIE nachtunen;
  Plateau hält OOS ohne Klippen. **rev-Parameter** stehen noch aus.
- ~~Reversal-Roadblock-Verschärfung~~ ERLEDIGT 14.7.: band/reclaim-Varianten fallen OOS durch;
  das eigentliche Messer-Problem waren die bcr/rev-Trades → via BCR_WT_ONLY=1 gelöst.
- ~~Pine v20 → v21~~ ERLEDIGT 14.7.: TBD_WM_SAR_v21_champion.pine (bcrWtOnly-Input, default an),
  live im TV-Slot „TBD Method Codex Fork v21" (Version 84) kompiliert.
- **Deployment:** server/-Paket gebaut (14.7.): Watcher+Bewerter+Kalibrier-Report, Shadow-Modus.
  Offen: launchd auf dem MacBook aktivieren, Briefing um `{"bias": ...}`-Zeile ergänzen,
  Binance-Signal ↔ Hyperliquid-Fill-Abgleich. Executor ERST nach bestandener Kalibrierung.
