# Evaluator-Ausfall-Befund (2026-08-12)

**TL;DR:** Kein aktueller Ausfall. Die 12 "fehlenden" Verdicts (12/46 = 26 %)
sind alle aus der Anfangs­phase 2026-07-14 bis 2026-07-21 und stammen aus einer
alten Policy, die `er_low`-Signale nicht bewertet hat. Ab dem 22. Juli
(Signal-ID 13, 2026-07-22 03:30) bekommt jedes Signal ein Verdict — inkl.
`er_low`. Keine Timeout-, JSON-Parse- oder API-Ausfälle.

## Rohdaten

- Signale gesamt: **46**
- Signale mit Verdict: **34**
- Signale ohne Verdict: **12** (alle IDs 1–12)

## Die 12 unevaluierten Signale

| ID | Zeitpunkt (UTC+2) | Tag | Gate | Dir | Px |
|---|---|---|---|---|---|
| 1 | 2026-07-14 09:45 | bcr | er_low | +1 | 62,529.7 |
| 2 | 2026-07-15 14:30 | mw  | er_low | −1 | 64,767.2 |
| 3 | 2026-07-16 05:30 | bcr | er_low | −1 | 64,636.2 |
| 4 | 2026-07-16 07:45 | bcr | er_low | +1 | 64,897.9 |
| 5 | 2026-07-16 18:15 | bcr | er_low | +1 | 64,515.8 |
| 6 | 2026-07-18 02:00 | bcr | er_low | +1 | 63,936.9 |
| 7 | 2026-07-19 15:30 | bcr | er_low | −1 | 64,393.8 |
| 8 | 2026-07-19 23:00 | bcr | er_low | +1 | 64,511.0 |
| 9 | 2026-07-20 01:00 | bcr | er_low | +1 | 64,669.6 |
| 10 | 2026-07-20 16:00 | bcr | er_low | −1 | 64,294.2 |
| 11 | 2026-07-20 16:15 | bcr | er_low | +1 | 64,441.2 |
| 12 | 2026-07-21 00:15 | bcr | er_low | +1 | 65,187.9 |

**Gemeinsamkeit**: **100 % gate=`er_low`**, alle vor dem 21.7.

## Erstes evaluiertes Signal

`id=13, 2026-07-22 03:30, mw/wt_macro` — ab hier bekommt jedes Signal (auch
`er_low`) ein Verdict.

## Gate-Verteilung (alle Signale)

| Gate | Anzahl | mit Verdict | ohne Verdict |
|---|---|---|---|
| er_low | 27 | 15 | **12** |
| wt_macro | 10 | 10 | 0 |
| bcr_wt_only | 9 | 9 | 0 |
| rev_l4 | 1 | 1 | 0 |

**Alle Nicht-`er_low`-Gates werden vollständig evaluiert.**

## `watcher.log`-Grep

```bash
grep -iE "NO_VERDICT|Evaluator-Fehler|timeout|json.*decode" watcher.log
```

Ergebnis: **2×** `NO_VERDICT`, **0×** Timeout, **0×** JSON-Fehler.
Die zwei `NO_VERDICT`-Fälle sind einzelne KI-Antworten die kein Score-Block
enthielten (fail-open hat korrekt gegriffen: score=null, kein Veto).

## Ursache

Beim Rollout 14.7. war die Policy: `er_low`-Signale = Setup-Kandidat kommt
gar nicht ans Gate (ER-Filter blockt vor Roadblock), also wurde auch der
Evaluator gespart. Am 22.7. wurde die Policy revidiert (nachvollziehbar in
`server/watcher.log` durch das plötzliche Verdict-Erscheinen bei `er_low`
ab id=13). Die 12 Vorher-Signale bleiben unevaluiert — kein Backfill nötig,
weil Outcomes (r24/r72/r168) für die Kalibrierung ausreichen und der
Bewerter zu diesem Zeitpunkt sowieso nicht prädiktiv war.

## Aktuelle Randbemerkungen (kein Ausfall, aber Optimierungspotenzial)

- Neuere Verdicts (id ≥ 283) beginnen mit "WebFetch nicht erlaubt" /
  "Live-Data-Tools nicht freigegeben". Der Evaluator versucht Live-Daten,
  fällt aber sauber auf Briefing-Daten zurück. Kein Ausfall, aber wenn
  gewünscht könnten dem Evaluator explizit Read-only-Tools (WebFetch für
  Preise, Funding) freigegeben werden.

## Vorschlag

Kein Handlungsbedarf. Die 12 Ausfälle sind historisch und erklärt.
Ausfall-Quote **aktuell 0 %**. Weiter beobachten; wenn die
`NO_VERDICT`-Zähler steigt, `EVAL_TIMEOUT` prüfen und den Prompt-Trailer
"gib IMMER einen JSON-Score" härten.
