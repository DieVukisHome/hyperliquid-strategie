# UMBAU-ANWEISUNG: Tagesanalyse-System (für den Server-Claude)

Verbindliche Anweisung nach dem Review von `trading_analysis_review/` (11.8.2026).
Befund: 76 Calls / 6 Wochen, direktionale Trefferquote 36%, Ø-Richtungs-Return
negativ in BEIDEN Richtungen (Long −0,56%, Short −0,52%). Gleichzeitig blockte die
deterministische Engine 46 Signale mit Counterfactual-Summe ≈ −40R.
Konsequenz: Das LLM erzeugt keine Signale mehr. Es berichtet und bewertet nur.

## 1. Setup-Card-Generator STILLLEGEN

In `trading_analysis.py`:
- Den kompletten Analyse-Prompt (12,7KB: Regeln A–H, Setup-Katalog 8 Typen,
  Setup-Card-Format, Loop-Check-Prosa, KLARTEXT-Block) ERSATZLOS entfernen.
- Cron-Zeiten (08:00, 14:00) und Telegram-Versand BEHALTEN.
- Die Datenerhebung (Binance/Kiyotaka/TBD-Hyblock) BEHALTEN — sie wird Input
  für berechnete Labels (Punkt 3), nicht mehr für den LLM-Prompt-Rohtext.

## 2. Neuer Ablauf pro Cron-Lauf

```
python3 server/daily_context.py --md   # Engine-Read + Funding/OI/F&G, deterministisch
→ LLM schreibt Report nach ANALYSE_PROMPT.md-Schema (≤300 Wörter, 4 Abschnitte)
→ Pflicht-Endzeile: {"bias": "long|short|neutral", "confidence": "...", "invalidation": <preis>}
→ Ablage server/analysen/YYYY-MM-DD_HHh.md
→ Telegram bekommt DIESEN Report (keine Setup-Card, keine Entry/SL/TP-Angaben)
→ track_record.json weiter füttern: timestamp, price_at, bias, 24h-Outcome wie bisher
```

Der Report ist eine PROGNOSE für den Backcheck, keine Handelsanweisung.
Formulierungen wie "Entry", "SL", "TP", "Setup" sind im Report VERBOTEN.

## 3. Interpretation aus dem Prompt in den CODE verlagern

Rohdaten nie mehr interpretierbar ans LLM geben. In der Datenerhebung berechnen:

```python
# Beispiel Liquidations-Semantik (der 48h-Aggregat-Fehler vom 11.8.):
liq_label = (
  f"48h-AGGREGAT (nicht aktueller Move): Long-Liqs ${long_liq/1e6:.1f}M, "
  f"Short-Liqs ${short_liq/1e6:.1f}M. Aktueller Move: Preis "
  f"{'faellt' if px_chg_4h < 0 else 'steigt'} {px_chg_4h:+.1f}% -> "
  f"{'LONGS' if px_chg_4h < 0 else 'SHORTS'} werden aktuell liquidiert.")
```

Gleiches Prinzip für OI-Delta vs Preis (Divergenz-Label berechnen), Funding-Regime,
Retail-Positionierung. Das LLM bekommt fertige Sätze, keine Zahlenreihen.

## 4. Loop-Check in den CODE

```python
prev = json.load(open('last_call.json'))          # {"bias": ..., "price": ...}
delta = (price_now / prev['price'] - 1) * 100
sign = {'long': 1, 'short': -1}.get(prev['bias'], 0)
verdict = ('kein Richtungs-Call' if sign == 0 else
           'RICHTIG' if delta * sign > 0 else f'FALSCH (Δ {delta:+.2f}% gegen Bias)')
# -> als unveraenderlicher Fakt in den Prompt: "Vorheriger Call: {bias} @ {price} — {verdict}"
```

Das LLM bewertet sich NIE selbst. Watch-mit-Richtung zählt in diesem Code als
Richtung (long-watch → 'long').

## 5. Track-Record BEHALTEN

Mechanismus unverändert (er hat den Edge-Mangel sauber gemessen — das ist sein Job).
Er scored jetzt die Report-Bias-Zeile. Auswertung läuft über
`calibration_report.py` (Briefing-Backcheck) mit.

## 6. Evaluator: Ausfallrate klären

12 von 46 Signalen haben KEIN Verdict (fail-open hat korrekt gegriffen, aber die
Quote ist zu hoch). Prüfen: `grep -i "NO_VERDICT\|Evaluator-Fehler" server/watcher.log`
und die `raw`-Spalte der verdicts-Tabelle. Typische Ursachen: Timeout (EVAL_TIMEOUT
erhöhen), API-Limit, JSON nicht am Antwort-Ende. Befund als Datei
`server/analysen/evaluator_ausfaelle.md` committen.

## 7. Unverändert gültig (nicht neu verhandeln)

- Engine-Code + Watcher-CHAMP-Config sind READ-ONLY (Config-Guard schlägt sonst an).
  Engine-Änderungen nur nach lokaler 4J+OOS-Validierung durch Wookie/Cowork-Claude via Commit.
- Bewerter bleibt Shadow, nur abwerten, fail-open. Aktuelle Kalibrierung (N=17):
  Scores NICHT prädiktiv (oberes Terzil ØR168 −3,3) → erst recht kein Veto, keine
  Gate-Overrides. Weiter sammeln.
- journal.db nur lesend; Export ausschließlich via `journal_export.py`.
- Keine Trades, keine Orders, keine Transfers — unter keinen Umständen.

## Abnahme

Fertig, wenn: (a) ein Cron-Lauf einen Report nach Schema in `server/analysen/`
erzeugt und pusht, (b) Telegram den Report ohne Setup-Card zeigt, (c) `last_call.json`
+ Code-Loop-Check aktiv, (d) Evaluator-Ausfall-Befund committed. Danach kurze
Vollzugsmeldung als Commit-Message.
