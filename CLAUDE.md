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
REV_1D=0.066  REV_4H=0.033  REV_1H=0.0165     # ZigZag rev% pro TF (Marktstruktur/BoS)
ER_N=30  ER_MIN=0.20                          # Efficiency-Ratio-Clarity-Filter auf 4h
VEC_MULT=99 (M/W-Vektor-P1/P3 AUS)  LV_VEC_MULT=1.5 (Level-Vektor)
MTF_MACRO=1  MTF_RBTOL=0.005                  # 1D-Makro-Gate; Roadblock-Toleranz 0,5%
RISK=0.01  MAX_LEV=10                          # 1% Risiko/Trade; optional VT_ON (Vol-Targeting 0.3-1.0)
```

Gate-Logik: Bias = 4h-BoS-Trend. **With-Trend** wenn 1h-Level<3 (+1D-Makro-Zustimmung);
**Reversal** (Counter-Trend) nur an 4h-Level-3 + Roadblock (HOW/LOW/HOD/LOD ±0,5%);
Entry nur wenn 4h-ER ≥ 0,20 (Clarity). Exit = reiner SAR-Runner (kein TP), Flip aufs Gegensignal.

## Dateien

- `wm_sar_mtf.py` — die **Champion-Engine** (Backtester). Alle Parameter via Umgebungsvariablen.
- `levels_mtf.py` — Multi-TF Level/Struktur-Engine (BoS-Trend, Level-State, Efficiency Ratio, Key-Levels). Wird von wm_sar_mtf importiert.
- `cycle_counter.py` — TBD-Zyklus-Zähler (KONTEXT-Tool, KEIN Trade-Trigger; mechanisiert nicht in Edge, dient nur als grobe Zyklus-Anzeige).
- `run_mtf_compare.py` — Vergleich Champion vs Baseline (4J + IS/OOS-Split).
- `wm_sar_mtf_walkforward.py` — Walk-Forward über die Level-Detektions-Params.
- `TBD_WM_SAR_v20_champion.pine` — Pine-`strategy()`-Port (TradingView), Einzelposition, mit Markern.
- `backtest/fetch_binance_data.py` — Daten holen (Binance public Futures-API, kein Key).

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
- **Formaler Walk-Forward** von ER_MIN/rev (Plateaus gesehen, aber nicht IS-blind bestätigt).
- **Reversal-Roadblock** ist locker (feuert wenn Preis *unter* Wochen-/Tagestief statt *daran*) —
  fängt fallende Messer; „nahe am Level"-Verschärfung testen.
- **Deployment:** Watchdog/Heartbeat für den always-on Server; Binance-Signal ↔ Hyperliquid-Fill-Abgleich.
