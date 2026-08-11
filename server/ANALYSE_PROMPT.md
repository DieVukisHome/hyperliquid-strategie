# Tägliche BTC-Analyse — Arbeitsanweisung für den Server-Claude

Ziel: eine kurze, KONSISTENT strukturierte Tagesanalyse als Grundlage für den
KI-Bewerter und den Briefing-Backcheck. Kein freies Essay — festes Schema.

## Ablauf (jeden Tag, 08:00)

1. Kontext holen — NICHT selbst Daten zusammensuchen, das Script liefert alles:
   ```bash
   python3 server/daily_context.py --md > /tmp/ctx.md
   ```
   Schlägt eine Quelle fehl, steht das im Kontext (`_err`) — dann diese Quelle im
   Text als "n/a" führen, NICHT raten und NICHT anderweitig beschaffen.

2. Analyse schreiben nach `server/analysen/YYYY-MM-DD.md` — EXAKT diese Struktur:

   ```markdown
   # BTC Tagesanalyse YYYY-MM-DD

   ## Engine-Lage (aus dem Kontext, nicht interpretieren)
   2-3 Sätze: Bias/Level/ER/Position/Signale-48h wiedergeben.

   ## Orthogonale Daten
   2-3 Sätze: Funding, OI-Änderung, Fear&Greed — mit den KONKRETEN Zahlen.

   ## Zyklus-Read (Interpretation)
   3-5 Sätze: Wo im TBD-Zyklus stehen wir? Key-Level-Nähe, TF-Agreement/
   Disagreement, was würde den Read invalidieren (konkretes Preisniveau).

   ## Erwartung heute
   2-3 Sätze: wahrscheinlichstes Szenario + Alternativszenario.

   {"bias": "long|short|neutral", "confidence": "low|med|high", "invalidation": <preis>}
   ```

3. Die JSON-Zeile am Ende ist PFLICHT (maschinenlesbar für calibration_report
   Briefing-Backcheck). `bias` = erwartete 24h-Richtung, nicht Wunschrichtung.

4. Committen und pushen (analysen/ und export/ sind absichtlich NICHT ignoriert):
   ```bash
   python3 server/journal_export.py
   git add server/analysen server/export
   git commit -m "Tagesanalyse + Journal-Export $(date +%F)"
   git push origin main
   ```

## Regeln

- Analyse ≤ 300 Wörter. Zahlen aus dem Kontext zitieren, keine eigenen Schätzungen.
- Die Analyse ÄNDERT NICHTS an Engine/Config — sie ist Kontext für den Bewerter
  und Wookies Morgenlektüre. CHAMP-Config und Engine-Code sind read-only
  (Config-Guard schlägt sonst an).
- Kein Zugriff auf journal.db schreibend. Export nur via journal_export.py.
- Wenn daily_context.py selbst fehlschlägt: Fehler in die Analyse-Datei schreiben
  und pushen — ein leerer Tag ist ein Datenpunkt, ein erfundener nicht.
