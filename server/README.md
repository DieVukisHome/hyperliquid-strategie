# server/ — Signal-Watcher + KI-Bewerter (Shadow-Modus)

Asymmetrische Bewerter-Schicht gemäß CLAUDE.md-Leitplanke 3: die deterministische
v21-Engine erzeugt Signale, Claude bewertet sie mit orthogonalen Daten. **Kein
Order-Code — reine Beobachtung + Journal.** Ein Executor kommt erst nach bestandener
Kalibrierung (unterstes Score-Terzil über ≥50 Setups messbar schlechter).

## Komponenten

- `signal_watcher.py` — Dauerlauf (launchd). Hält Binance-15m-Daten aktuell, läuft die
  v21-Engine pro Kerze, loggt ALLE Signal-Events (auch gate-geblockte, ~1-2/Tag) in
  `journal.db`, ruft bei neuen Events den Bewerter. Heartbeat-File pro Zyklus.
- `evaluator.py` — Hook: `claude -p` (+ optional Hermes via `HERMES_CMD`) mit RUBRIK.md
  + Event-JSON + jüngstem 8:00-Briefing. Verdict (score/veto/size_factor≤1) ins Journal.
  Fail-open: kein/ungültiges Verdict → size_factor 1.0.
- `RUBRIK.md` — Bewertungs-Rubrik (Asymmetrie, Veto-Mathematik, orthogonale Quellen,
  Verdict-Schema). Das ist der "Prompt-Vertrag" — Änderungen hier ändern den Bewerter.
- `calibration_report.py` — wöchentlicher Report: Score-Terzile vs realisierte R,
  Veto-Counterfactuals, claude/hermes-Disagreement, Briefing-Backcheck.

## Setup auf dem Server (MacBook)

```bash
cd ~/pfad/zum/repo && git pull
python3 server/signal_watcher.py --once          # Erstlauf: holt ~4J Daten (dauert etwas)
python3 server/signal_watcher.py --once          # zweiter Lauf: sollte "0 neue Bars"-nah sein

# launchd: REPO_DIR + BRIEFING_DIR in beiden plists ersetzen, dann:
cp server/launchd/*.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.hypertrading.watcher.plist
launchctl load ~/Library/LaunchAgents/com.hypertrading.calibration.plist

tail -f server/watcher.log                        # zuschauen
python3 server/calibration_report.py              # Report manuell
```

Voraussetzungen: `claude` CLI eingeloggt (läuft schon fürs Briefing), Python 3 (stdlib,
keine Pakete). Watchdog-Idee: das 8:00-Briefing prüft `server/heartbeat` (< 30 min alt?)
und meldet sonst "Watcher down".

## Briefing-Integration

Der Bewerter hängt automatisch das jüngste File aus `BRIEFING_DIR` an. Damit der
Backcheck im Wochen-Report funktioniert, ans Briefing eine Zeile anhängen:
`{"bias": "long"}` bzw. `{"bias": "short"}` (oder "bullish"/"bearish" im Text reicht).

## Wichtige Invarianten (nicht aufweichen)

1. Bewerter kann nur senken: `size_factor` wird auf [0, 1] geclampt, veto nur abwertend.
2. Fail-open: Bewerter-Ausfall darf nie ein Signal blockieren.
3. Shadow zuerst: Verdicts beeinflussen nichts, bis der Kalibrier-Report Diskriminierung
   über ≥50 Setups zeigt UND die Veto-Counterfactuals netto negativ sind.
4. Veto-Mathematik: 1 gefressener 27R-Runner = 27 gerettete Stops. Vetoquote <5%.
