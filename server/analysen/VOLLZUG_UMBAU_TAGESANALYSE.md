# Vollzug: UMBAU_TAGESANALYSE (2026-08-12)

Alle 7 Punkte der Anweisung umgesetzt. Erster produktiver Lauf des neuen
Systems: `server/analysen/2026-08-12_08h.md` (commit `91a6993`).

## Umgesetzt

| # | Anweisung | Umsetzung |
|---|---|---|
| 1 | Setup-Card-Generator stilllegen | `analyse_with_claude()` (12,7 KB Prompt) aus `~/.hermes/scripts/trading_analysis.py` entfernt. Cron + Telegram + Datenerhebung behalten. |
| 2 | Neuer Ablauf pro Cron-Lauf | `main()` neu: `daily_context.py --md` → LLM-Report nach `ANALYSE_PROMPT.md`-Schema → `server/analysen/YYYY-MM-DD_HHh.md` → Telegram → commit/push. |
| 3 | Interpretation in Code | Neue Funktion `build_labels(raw)` — deterministische Sätze für Liq-Semantik (48h-Aggregat vs aktueller Move), OI-Delta-Divergenz, Funding-Regime, Retail-Positionierung, Bid/Ask-Delta, Cumul.Liq-Delta. |
| 4 | Code-Loop-Check | `loop_check_fact(price_now)` liest `server/last_call.json`, berechnet deterministisch RICHTIG/FALSCH. Watch-mit-Richtung zählt als Richtung (`"long" in bias` → Long-Call). `save_last_call()` schreibt nach jedem Lauf. |
| 5 | Track-Record | Unverändert bei `~/.hermes/trading_analyses/track_record.json`. Speist sich jetzt aus der JSON-Endzeile des Reports (`extract_bias_json`), nicht mehr aus Setup-Card-Regex. |
| 6 | Evaluator-Ausfälle | `evaluator_ausfaelle.md` in `server/analysen/`. Befund: 12/46 = 0-er_low-Signale aus Anfangs­phase 14.–21.7. (alte Policy), aktuelle Ausfall-Quote 0 %. Kein Handlungsbedarf. |
| 7 | Unverändert gültig | Engine-Code + CHAMP-Config nicht angefasst. Bewerter bleibt Shadow. Journal.db nur lesend (Export via `journal_export.py` im Cron-Push mitgezogen). Keine Trades. |

## Abnahme-Kriterien

- [x] Cron-Lauf erzeugt Report nach Schema in `server/analysen/`
- [x] Telegram zeigt Report ohne Setup-Card
- [x] `last_call.json` + Code-Loop-Check aktiv (Loop-Check-Zeile lautet beim
      ersten Lauf: *"kein vorheriger Call (erster Lauf)"* — ab morgen scharf)
- [x] `evaluator_ausfaelle.md` committed

## Report-Beispiel (erster Lauf)

- Bias: **neutral**, confidence **low**, invalidation **63,212**
- Kein Wort "Entry/SL/TP/Setup" im Report
- Loop-Check-Zeile aus dem Code stammend (nicht neu bewertet)
- 5 Labels (Liq/OI-Delta/Funding/Retail/Bid-Ask) mit fertigen Sätzen
- Fußzeile: Deterministischer Kontext + Labels + Loop-Check im
  `<details>`-Block für Debug

## Bekannte Randbemerkungen (nicht blockierend)

- Doppelter `# BTC Tagesanalyse ...`-Header (einmal Skript-Wrapper, einmal
  vom LLM aus dem Schema übernommen). Kosmetik — kann bei nächstem Touch
  entfernt werden.
- Neuere Bewerter-Verdicts erwähnen "WebFetch nicht erlaubt" — im
  `evaluator_ausfaelle.md` beschrieben. Optimierung: Read-only-Tools für
  Preise/Funding an den Bewerter durchreichen, wenn gewünscht.
