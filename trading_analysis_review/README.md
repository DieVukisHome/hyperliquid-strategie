# Trading-Analyse Review — Bitte durchgehen und ehrliches Urteil

## Kontext

Ein selbstgebautes Trading-Analyse-System läuft seit Wochen. Es sammelt Marktdaten
aus mehreren APIs (Binance, Kiyotaka, TBD/Hyblock) und schickt einen strukturierten
Prompt an **Claude Sonnet 4.6** (via `claude --print`). Ergebnis: eine Analyse mit
Setup-Card, die auf Telegram landet. Läuft im Cron 08:00 + 14:00 + on-demand.

Der Nutzer (erfahrener Trader, 3 Jahre HL-Erfahrung) sagt nach mehreren Wochen Betrieb:

> **Die Analysen bringen gar nichts. Kein Mehrwert. Keine richtigen Setups. Die
> Daten werden falsch interpretiert. Der Loop-Check funktioniert nicht. Die Regeln
> sind nicht nachvollziehbar. Die Sprache ist irreführend. Ich dachte, eine KI kann
> das besser. Vielleicht ist der Prompt ein Overload.**

## Auftrag an dich (das externe Modell)

Bitte lies dich in die Dateien ein und liefere ein **ehrliches, hartes Urteil**:

1. **Ist der Prompt Overload?** (12.7 KB Prompt-Text + ~30 KB Rohdaten-Summary =
   ~14k input tokens jedes Mal — inklusive 8 Regeln A–H, 8-typiger Setup-Katalog,
   4-Zeilen-Loop-Check, 3 Pflicht-Datenblöcke, KLARTEXT-Verbotsliste, harte Formatvorgaben.)
2. **Sind die 8 Regeln A–H konsistent und trainierbar für ein LLM?** Oder widersprechen
   sie sich / überlagern sich?
3. **Falsche Interpretation der Rohdaten** — konkretes Beispiel im 18h-Output
   (2026-08-11): Die AI behauptet im KLARTEXT "die schwachen Hände auf Short-Seite
   wurden bereits massenhaft liquidiert" während der Preis gerade −1.4% gefallen ist.
   Das ist physikalisch falsch — fallender Preis liquidiert Longs, nicht Shorts.
   Die "Short-Liq $26.3M" ist ein **48h-Aggregat**, nicht der aktuelle Move. Wie
   verhinderst du diese Verwechslung im Prompt-Design?
4. **Loop-Check ist zu schwach.** Beispiel Loop-Check im 18h-Output:
   *"vorheriger Bias neutral → kein Directional-Call; keine Richtungsbewertung möglich."*
   Der vorherige Bias war aber "Neutral, **Contrarian-Long-Watch**" — Watch mit
   Direction. Die AI umgeht die Anti-Rationalisierungs-Regel H, indem sie nur "Neutral"
   zitiert. Wie machst du das wasserdicht?
5. **Setups oft R:R <1.5** trotz Vorgabe "Nur TPs mit R ≥1.0 akzeptabel". Bringt der
   Setup-Katalog (8 Typen) überhaupt was, oder erzwingt er nur schlechte Trades weil
   die AI meint sie MUSS einen Typ wählen?
6. **Grundsatzfrage:** Kann ein einziges LLM-Call mit 14k Tokens Input überhaupt
   *handelbare* Signale liefern, oder brauchst du eine mehrstufige Pipeline
   (z.B. Data-Sanity-Check → Regime-Detection → Setup-Selektion) mit je einem
   spezialisierten Prompt? Wenn ja, wie sähe das aus?

## Was der Nutzer NICHT will

- Kein "einfach mehr Kontext geben" — Prompt ist eher zu voll als zu leer.
- Keine kosmetische Änderung (Formatierung, Emoji-Reduktion, andere Reihenfolge).
- Keine "AI kann das schon" Ausflüchte — wenn du das Setup für nicht sinnvoll hältst,
  sag das direkt.
- Kein "füge diese Regel noch hinzu" — die 8 Regeln sind schon Teil des Problems.

## Was gewünscht ist

- **Harte Diagnose**: was ist strukturell kaputt, was ist Feature-Frage.
- **Vorschlag**: entweder Prompt radikal vereinfachen (welche Teile weg?), oder
  komplette Neu-Architektur (welche Stages?).
- **Realistische Erwartung**: welchen Anteil handelbarer Setups kann ein LLM
  bei diesem Datenlayout liefern? Sub-1%? 5%? 20%?

## Dateien in diesem Ordner

| Datei | Zweck |
|-------|-------|
| `README.md` | Dies. |
| `prompt.md` | Der komplette Prompt-Text, wie er an Claude geschickt wird. Placeholder `<<...>>` markieren die dynamischen Einsetzungen. |
| `sample_summary.md` | Beispiel-Rohdaten-Block (der `<<SUMMARY_TEXT>>` im Prompt). Das ist der 18h-Lauf vom 2026-08-11. |
| `outputs/*.md` | **Alle 73 Analyse-Ausgaben** (chronologisch von 2026-07-xx bis 2026-08-11). Jede enthält oben die Rohdaten (Summary) und unten die KI-Antwort. |
| `track_record.json` | Track-Record des Analyse-Systems: jede gespeicherte Setup-Card mit Bias, Preis, Setup-Typ und Outcome (evaluated_at, delta_pct nach ≥24h). Basis für die "Ø-Return pro Bias"-Zahlen im Prompt-Header. |
| `engine_journal.json` | **Deterministische Engine (v22 Champion)** — komplettes Journal: 46 Signale, 34 KI-Verdicts (via `evaluator.py`, ebenfalls Claude-basiert), 46 Outcomes (r24 / r72 / r168, exit_reason). Jedes Signal enthält `signal + verdict + outcome` gejoint. So kannst du sehen wie die Engine-Signale + die zweite KI-Bewertungsschicht performt haben. |
| `code/trading_analysis.py` | Das Python-Script komplett (Datenerhebung + Prompt-Assembly + Telegram-Versand). Nur zur Referenz — der eigentliche Prompt steht in `prompt.md`. |

## Kontext-Daten die im Summary stecken

Für jeden Coin (aktuell nur BTC): 4H/Daily/Weekly OHLCV + RSI + EMA-Stack; 1H-Struktur
(letzte 8 Kerzen); 15M-Struktur (letzte 8 Kerzen); Funding + Perp-Basis + Order Book;
CVD + Large Trades; OI 48h; Reference Levels (PDH/PDL/PDC/Weekly-Open/VWAP); Kiyotaka
Liquidations-Aggregat 48h; **komplette TBD-Heatmap-Cluster (1d + 3d + 7d + 1M innerhalb
±8% Preis)** — hunderte Zeilen; **alle Liq-Levels high+medium** (mehrere hundert);
Cumulative Delta; TBD Funding 5h; **Retail Long/Short % 10h**; **OI-Delta 10h**;
**Bid/Ask-Delta 10h**; Global High-Impact-Events (ForexFactory).

Zusätzlich im Prompt-Header: **Track Record** (letzte 10 Calls, Hit-Rate,
Ø-Return pro Bias) + **vorherige Analyse** (für Loop-Check).

## Nutzer-Hintergrund (relevant für den Ton der Analyse)

- Tradet BTC/HL-Perps seit 3 Jahren, kann Charts lesen, braucht keine Fachbegriff-Vermeidung
  für sich selbst.
- Hat gleichzeitig eine deterministische Engine laufen (`wm_sar_mtf.py`, v22 Champion) —
  das hier soll ein **komplementärer Bewerter** sein, kein Konkurrent zur Engine.
- Ist frustriert weil er die Zeit reinsteckt und keinen Mehrwert sieht.
