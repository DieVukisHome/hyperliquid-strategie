# TBD-Snapshot-Schnittstelle (Heatmap/Liq-Levels → Bewerter + Tages-Report)

Auftrag an den Server-Claude: Die bestehende Datenerhebung (TBD-Chrome-Extension:
Heatmap-Cluster, Liq-Levels, Kiyotaka-Liq-48h, Retail L/S, OI-Delta, Bid/Ask-Delta)
schreibt bei JEDEM Lauf zusätzlich einen Snapshot nach:

```
server/data/tbd_snapshot.json        (liegt in .gitignore — bleibt lokal, wird NICHT gepusht)
```

## Schema (exakt einhalten — daily_context.tbd_snapshot() parst das)

```json
{
  "ts": 1786000000,
  "price": 63821.0,
  "heatmap": {
    "1d": [{"px": 63350.0, "size": 8810, "side": "long"}],
    "3d": [{"px": 63150.0, "size": 14110, "side": "long"}],
    "7d": [{"px": 63460.0, "size": 30714, "side": "long"}],
    "1M": [{"px": 65000.0, "size": 50000, "side": "short"}]
  },
  "liq_levels": [{"px": 63401.0, "usd": 10000000, "lev": "high"}],
  "liq_48h": {"long_usd": 28200000, "short_usd": 3900000},
  "retail_long_pct": 62.0,
  "oi_delta_10h_usd": -13400000,
  "bidask_delta_10h_usd": 109600000
}
```

Nur Cluster/Levels innerhalb ±8% des Preises schreiben (mehr wird ohnehin verworfen).
`side` = welche Seite dort liegt (long-Cluster unter Preis = Support/Magnet).

## Was daraus wird (bereits implementiert, Commit-Stand beachten)

`daily_context.market_context(price)` liest den Snapshot fail-soft und liefert
KOMPAKT (kein Rohdaten-Dump — das war der alte Overload-Fehler):
- Top-3-Cluster über/unter Preis (±5%), nach size sortiert, mit Distanz-%
- die 6 nächsten Liq-Levels mit USD + Leverage-Klasse
- liq_48h-Aggregat + Retail/OI-Delta/BidAsk-Rohwerte
- `age_min` + VERALTET-Warnung bei >30 min (Bewerter behandelt als n/a)

Das fließt automatisch in (a) den Bewerter-Prompt (evaluator.py injiziert) und
(b) den Tages-Report-Kontext. Wenn der Snapshot fehlt, läuft alles wie bisher
weiter (fail-soft) — es gibt also keinen Grund, den Watcher dafür anzuhalten.

## Frische

Snapshot bei jedem Cron-Lauf (08:00/14:00) aktualisieren UND — wichtiger — 
ein leichtgewichtiger Refresh alle 15 min, damit Signal-Events (kommen zu
beliebigen Zeiten) frische Cluster sehen. Wenn die Extension nur im
Browser-Kontext liefert: Refresh so oft wie praktikabel, VERALTET-Regel
fängt den Rest.

## Abnahme

Ein Signal-Event nach Einbau → Verdict-`reasoning` zitiert konkrete Cluster
(z. B. "SL 0,2% vor $34M-Liq-Cluster = Stop-Hunt-Risiko"). Kurze Vollzugsnotiz
als Commit-Message genügt.
