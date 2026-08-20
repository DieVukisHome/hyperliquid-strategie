# Abnahmetest: Zyklus-Lesart (Wookie) vs Engine

Stand 20.8.2026. **Stufe 0 des HTF-Umbaus.** Diese Datei ist der eingefrorene
Referenz-Read von Wookie, gegen den jede neue Zyklus-Logik antreten muss —
festgelegt BEVOR Parameter gewählt werden (sonst fitten wir auf Einzelfälle).

Alle Zeiten UTC+2, Kerzen-Eröffnung. Daten: BTCUSDT Perp 15m, Binance Futures.

---

## Fall A — 4h-W Anfang August 2026 (der aktuelle Streitfall)

**Wookies Read:** 4h-W mit P1 03.08, P3 14.08. Dazwischen auf 1h ein vollständiger
Abwärtszyklus mit drei Stufen — das ist die *rechte Seite* des 4h-W.

| Rolle | Zeit | Kurs | Kerzen-Merkmale |
|---|---|---|---|
| **4h-P1** | 03.08 10:00 | Tief **62.268** | Docht 46%, Body 10%, Vol 1,52× — knapp KEINE SVC (P1 = Trap, nicht Erschöpfung) |
| 1h M-P3 (Zyklusstart) | 10.08 10:00 | 65.160 | Beginn des Abwärtsbeins |
| 1h Stufe 1 | 10.08 20:00 | Tief **63.788** | |
| 1h Retrace-Hoch | 11.08 14:00 | 64.470 | Board-Meeting, Vol 2,32× |
| 1h Stufe 2 | 11.08 20:00 | Tief **63.222** | Vol 1,73× |
| 1h Stufe 3 (Live-Lesart) | 13.08 18:00 | Tief 62.800 | Vol **4,85×** — hier hätte man live L3 gelesen; es kam aber KEIN W → **Extension** |
| 1h Stufe 3 final | 14.08 16:00 | Tief **62.484** | |
| **4h-P3 (SVC)** | 14.08 14:00 | Tief **62.484** | Docht 61%, Body 21%, Vol 1,90× — **SVC** |

**Konsistenz-Checks (bestanden):**
- Fallende Tiefs: 63.788 > 63.222 > 62.484 — monoton.
- 1h-Stufe-3-Tief (62.484) liegt ÜBER dem 4h-P1 (62.268) → höheres Tief → 4h-W gültig.

**Was die Engine (v22/v29) daraus macht — die Lücke:**

| | Wookie | Engine |
|---|---|---|
| 4h-Trend 04.08–14.08 | Abwärts (rechte W-Seite) | 04.08 18:00 −1 · 10.08 14:00 Stufe 1 · **11.08 18:00 dreht auf +1** |
| 1h-Zyklus 10.08–14.08 | 3 Stufen ABWÄRTS | 09.08 −1/St.2 · **10.08 17:00 dreht auf +1** · 12.08 St.1 · 12.08 St.2 (aufwärts) |
| Stufen bis zum Tief | 3 | 4h: 1 · 1h: 0 (zählt aufwärts) |

Die Engine flippt den 1h-Trend **innerhalb von Wookies Stufe 1** (10.08 17:00, vor
dem Stufe-1-Tief um 20:00) und den 4h-Trend **drei Tage vor P3**. Ursache ist der
kausale ZigZag (REV_1H 1,65% / REV_4H 3,3%): er dreht bei jedem Gegenschwung, statt
den Abwärtszyklus bis zum Ende (3 Stufen + Reversal-Formation) durchzuhalten.

**Folgerung:** Die Lücke liegt NICHT in der Formationserkennung (P1/P3 werden gefunden,
siehe Fall B), sondern in der **Zyklus-Buchführung**. Das deckt sich mit Wookies
Modell vom 3.7.: *„P1 = Invalidierung, FEST für den ganzen Zyklus, wandert NIE"* —
Reset nur bei Close über P1 oder nach vollendetem 3-Stufen-Zyklus + Reversal.

---

## Fall B — 1.7.2026 (Formationserkennung funktioniert bereits)

| Rolle | Zeit | Kurs | Merkmale |
|---|---|---|---|
| 4h-P1 | 01.07 02:00 | Tief **57.759** | Docht 55%, Body 37%, Vol 1,56× — **SVC** |
| 1h-P1 (SVC) | 01.07 03:00 | Tief **57.759** | Docht 64%, Body 16%, **Vol 5,21×** — SVC |
| 1h-P3 | 01.07 14:00 | — | Engine-Detektor bestätigt: `W, P1=57.759` ✓ |
| 15m-P3 | 01.07 14:45 | — | |

**Befund:** `detect_mw_htf()` auf 1h reproduziert Wookies Read exakt (P1 und P3
stimmen auf die Kerze). Der Baustein existiert also, wird aber nicht als
Anker/Trigger genutzt. Unterschied zu Fall A: dort sitzt die SVC nur auf 4h
(1h-Kerze 14.08 16:00 hat nur 33% Docht) → Anker muss **„SVC auf 1h ODER 4h"** sein.

---

## SVC-Definition (aus beiden Fällen abgeleitet)

**SVC = Hammer + Vektor** auf dem jeweiligen TF:
- Docht in Trendrichtung ≥ 50% der Kerzen-Range
- Body ≤ 40% der Range
- Volumen ≥ 1,5× SMA10 der **vorherigen** 10 Kerzen (nicht inkl. aktueller — siehe v24-Fix)
- Close gegen die vorherige Richtung (Trap)
- am lokalen Extrem (≥ 4 Kerzen)

**Häufigkeit 4h, 4 Jahre BTC:** 193 Anker = 48/Jahr. Mit Kontext-Gate
(4h-Stufe 3 UND Anker gegen den 4h-Trend): **34 = 8,5/Jahr**, stabil
(2022: 7 · 2023: 9 · 2024: 6 · 2025: 7 · 2026: 5).
ABER: Beide Wookie-Fälle fallen durch dieses Gate, weil die Engine dort
Trend +1 / Stufe 0 liest → siehe Lücke oben.

---

## Abnahmekriterien für den Umbau

Eine neue Zyklus-Logik gilt als bestanden, wenn sie:
1. In Fall A zwischen 10.08 und 14.08 einen **Abwärtszyklus mit 3 Stufen** zählt
   (Tiefs ±0,3% bei 63.788 / 63.222 / 62.484) und P1 fest bei 62.268 hält.
2. In Fall B P1 = 57.759 und P3 = 01.07 14:00 (1h) liefert.
3. Die Extension am 13.08 (L3-Lesart ohne folgendes W) **nicht** als Zyklusende
   verbucht, sondern bis 14.08 16:00 weiterläuft.
4. Danach: 4J BTC + IS/OOS + Cross-Coin (ETH/VIRTUAL) mindestens auf
   Champion-Niveau (v22: BTC +460%/PF3,75/DD18%/OOS+63%).

**Warnung aus der Projekt-Historie:** `cycle_counter.py` (3.7.) hat genau das
versucht und war als Bias-Ersatz −53% gegen +328%. Die neue Logik darf den
BoS-Bias daher NICHT ersetzen, sondern nur (a) P1-Anker und (b) Stufenzähler
fürs Reversal-Gate liefern. Getaggt messen, bevor irgendetwas promoted wird.
