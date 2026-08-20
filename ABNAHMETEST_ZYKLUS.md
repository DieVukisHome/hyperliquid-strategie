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

## Fall C — Mai 2026, 4h-M (Short-Seite, vollständigster Fall)

**4h-P1 = Railroad Tracks statt SVC:**

| Zeit | O→C | Range | Body | Vol | |
|---|---|---|---|---|---|
| 06.05 10:00 | 81.333 → 82.485 | 1.549 | 74% | **2,09×** | bull |
| 06.05 14:00 | 82.485 → 81.656 | 1.436 | 58% | **1,76×** | bear |

Zwei gegenläufige Vektorkerzen, Ranges zu 93% gleich, die zweite nimmt 72% des
ersten Körpers zurück. Kein Docht → auf 4h **keine** SVC. **Eine Ebene tiefer schon:**
1h 06.05 13:00 — Docht oben **56%**, Body 39%, Vol **2,42×**, Hoch **82.829** =
exakt das 4h-P1-Hoch. Gleiches am 4h-P3 (10.05 22:00 Vol 4,79× bull / 11.05 02:00
Vol 2,58× bear = Railroad; 1h 11.05 01:00 Docht 63%, Vol 1,61× = SVC).

**1h-Abwärtszyklus (2 Stufen), mechanisch reproduziert:**

```
P1              06.05 13:00   82.829   (1h-SVC)
Stufe 1 Ende    07.05 19:00   79.462   Tief an der 200er (79.499), Docht_u 48%
Board Meeting   Hoch          80.332
Stufe 2 bricht  08.05 04:00   unter 79.462
Stufe 2 Tief    08.05 05:00   79.137   Hammer an der 200er (Docht_u 63%, Vol 1,23× — KEIN Vektor)
```

**1h-W danach:** P1 08.05 05:00 · P2 08.05 13:00 (Rücklauf an die 50er) ·
P3 08.05 15:00 (Vol 2,35×).

**1h-Aufwärtszyklus (3 Stufen) — hier zeigt sich die Kernregel:**

| | Zeit | Hoch | Vol | Docht oben |
|---|---|---|---|---|
| Stufe 1 Ende | 09.05 06:00 | 80.642 | 1,89× | **94%** |
| Stufe 2 Ende | 09.05 20:00 | 81.043 | 1,68× | **60%** |
| Stufe 3 Ende | 11.05 01:00 | 82.460 | 1,61× | **63%** |

Alle drei sind SVCs. **Keiner dieser Punkte trifft eine EMA** (auf keinem TF, ±0,4%) —
die 200er lag längst hinter dem Preis. Die Extrema steigen monoton, dazwischen jeweils
Rücklauf an die 50er.

**Fraktale Verschränkung:** 11.05 01:00 ist gleichzeitig 1h-Stufe-3-Ende, 4h-P3 und
neues 1h-P1 des Abwärtszyklus. Danach 1h-P3 am 11.05 18:00 bzw. 20:00.
**Die Engine findet dieses M selbst:** `P3-Kerze 11.05 18:00, P1 = 82.460` ✓
(Wookie nannte 20:00 — auch gültiger InvHammer mit 65% Docht; die Engine nimmt die frühere.)

---

## Fall D — 12./13.05.2026, Fortsetzung von Fall C (NICHT lehrbuchmäßig)

Wookies eigener „nicht-textbook"-Fall. Zeigt die Fraktalität über drei Ebenen und
den Unterschied zwischen Reset-M und Reversal-M.

**Nach dem 1h-P3 (11.05 20:00) — 1h-Stufe 1 = drei 15m-Drop-Level:**

| 15m | Zeit | Tief | Kerze |
|---|---|---|---|
| DL 1 | 12.05 03:30 | 80.661 | Docht_u 55%, Body 45%, **Vol 9,72×** |
| DL 2 | 12.05 13:15 | 80.444 | Docht_u 56%, Vol 1,36× |
| DL 3 | 12.05 18:45 | 79.801 | Docht_u 38%, Vol 3,16× |

Fallende Tiefs ✓. **Keine** der drei erfüllt die strenge SVC-Definition (Body zu groß /
Volumen zu klein / Docht zu kurz) — auf 15m reicht die **Ablehnung an sich**.
Board Meeting dazwischen: 12.05 **08:15** Rücklauf an die 15m-50er (Hoch 81.270 vs
50er 81.334 = **−0,08%**) — Toleranz nötig, exakte Berührung wird nicht erreicht.

**Parallel auf 1h:** dieselbe Bewegung ist EINE Stufe. Die gelbe 200er wurde am
12.05 15:00 erreicht (Tief 80.361 vs 200er 80.394), Tief 79.801 um 18:45 = „Stufe 1 am 1h".

**Board Meeting der 1h (auf 15m):** nur EINE Gegenstufe, nicht drei —

| | Zeit | Preis | |
|---|---|---|---|
| P1 vom W | 12.05 18:45 | 79.801 | = das DL-3-Tief |
| P3 vom W | 13.05 02:00 | 80.364 | |
| **RL 1** (einzige Rise-Stufe) | 13.05 03:45 | 81.168 | = Retest der 1h-50er |
| P1 vom Reset M | 13.05 05:45 | 81.268 | |
| P3 vom Reset M | 13.05 11:00 | **81.270** | Vol 4,30× — 2 $ ÜBER P1 = „Final Damage" |

**Dann drei schnelle Bursts abwärts mit steigendem Volumen (= 1h-Stufe 2):**

| | Tief | Zeit | Segment-Volumen |
|---|---|---|---|
| Burst 1 | 80.410 | 13.05 14:00 | 12.287 |
| Burst 2 | 79.432 | 13.05 16:00 | 34.141 ↑ |
| Burst 3 | 78.714 | 13.05 18:00 | 40.489 ↑ |

Monotone Volumen-Progression L1 < L2 < L3 = Klimax (steckt als `VFRAC` bereits in
`cycle_counter.py`, bisher ungenutzt).

**Drei neue Regeln aus Fall D:**

11. **Das Board Meeting der Elternebene kann auf dem Kind aus EINER Stufe bestehen** —
    „eine Elternstufe = drei Kindstufen" gilt für die Impulsphase, nicht fürs Board Meeting.
12. **Reset-M und Reversal-M sind dasselbe Muster, unterschieden allein durch die
    Zyklusposition.** Im Board Meeting (nach L1/L2) startet es die nächste Stufe;
    nach drei fertigen Stufen kehrt es den Elternzyklus um. Deshalb ist die
    Stufenzählung die Voraussetzung für die Bedeutungszuweisung — und deshalb ist
    BCR immer Continuation (v21-Befund), M/W aber beides.
13. **Volumen-Progression über die Stufen** (L1 < L2 < L3) als Klimax-Signatur.

**Toleranz-Lehre:** Retest-Prüfungen brauchen ~0,15% Toleranz (wie BCR_TOL), nicht
exakte Berührung. Mit Null-Toleranz meldet die Prüfung fälschlich „kein Board Meeting".

---

## Fall E — 13.–16.05.2026: die vollständige Kaskade über vier Ebenen

Fortsetzung von Fall D. Hier schließt sich der fraktale Kreis; das ist der
anspruchsvollste Abnahmetest, weil er nicht nur Vergangenheit reproduziert,
sondern eine **Erwartung** für die Zukunft ableitet.

**Board Meeting nach 1h-Stufe 2 (Retrace 13.–14.05), auf 15m:**

| | Zeit | Preis | Vol |
|---|---|---|---|
| P1 vom W (= DL 3) | 13.05 18:00 | 78.714 | 1,58× |
| P3 vom W? (1) | 14.05 05:45 | 78.869 | 1,95× |
| RL 1 | 14.05 07:45 | 79.962 | 1,97× |
| P3 vom W? (2) | 14.05 13:45 | 79.188 | 0,95× |
| **50er-Break** | 14.05 15:15 | 80.042 | **3,38×** |
| RL 2 | 14.05 17:00 | 81.135 | 2,12× |
| RL 3 | 14.05 19:00 | 81.999 | 1,48× |

Volumen der drei Rise-Bursts: 20.259 → 37.188 → 38.773 (**monoton steigend**).

**Die Invalidierungs-Prüfung — knapp bestanden:**

```
Original 1h-P3 (Invalidierungs-Marke):  82.098,9
P1 vom 15m-M (14.05 19:00):             81.999,0
                                        ──────────
                                          −99,9   →  KEINE Invalidierung
```

Hundert Dollar. Der 1h-Abwärtszyklus bleibt bei Stufe 2, der ganze Anstieg ist
Board Meeting — kein neuer Zyklus.

**Dann 15m-M und drei Stufen abwärts → 1h-Stufe 3 komplett:**

| 1h-Stufe | Preis | Zeit |
|---|---|---|
| Stufe 1 | 79.801,0 | 12.05 18:45 |
| Stufe 2 | 78.713,8 | 13.05 18:00 |
| Stufe 3 | **77.601,8** | 16.05 10:00 |

**Und der Kreis schließt sich auf 4h:**

```
16.05 10:00   Tief 77.602   4h-200er 77.793   Abstand −0,25%   ← 200er erreicht
4h-P3 vom M   11.05 02:00   Hoch 82.350
4h-Stufe 1    = −5,8% bis 77.602 (= 4h-200er)
```

**Drei 1h-Stufen = EINE 4h-Stufe**, und diese 4h-Stufe 1 endet exakt an der gelben
4h-200er. Die vollständige Kaskade:

```
4h-P3 vom M         11.05 02:00   82.350
  4h-Stufe 1                      77.602  (4h-200er, 16.05 10:00)
    1h-Stufe 1                    79.801  (12.05 18:45)   ← je 3 15m-Stufen
    1h-Stufe 2                    78.714  (13.05 18:00)
    1h-Stufe 3                    77.602  (16.05 10:00)
```

**Wookies abgeleitete Erwartung:** Nach einer fertigen 4h-Stufe folgen noch zwei —
also zuerst ein Board Meeting auf 4h (auf 1h sichtbar als Retrace mit **Reset-M**),
dann 4h-Stufe 2 und 3.

**Regel 14 — Invalidierung:** Bezugspunkt ist das **P3 der Elternebene**. Wird es
nicht überschritten, bleibt die Zählung gültig, egal wie weit der Retrace läuft.
Unterschreitung um Haaresbreite genügt (hier 0,12%).

**Regel 15 — die 200er-Regel ist richtungsabhängig, nicht ebenenspezifisch:**
Stufe 1 endet an der 200er, **wenn diese in Laufrichtung liegt**. Belegt abwärts
auf 1h (Fall C) und abwärts auf 4h (Fall E). Lag die 200er hinter dem Preis
(Aufwärtszyklus Fall C), endete die Stufe stattdessen an der SVC.

**Regel 16 — P3 muss nicht sofort eindeutig sein:** Zwei P3-Kandidaten können
nebeneinander stehen (hier 05:45 und 13:45). Erst der nachfolgende **50er-Break
mit Volumen** (3,38×) entscheidet, welcher gilt.

**Regel 17 — Größe des Board Meetings bestimmt die Zahl der Kindstufen:** Reicht
der Retrace nur bis zur Eltern-50er, genügt EINE Kindstufe (Fall D). Läuft er bis
knapp unter das Eltern-P3, sind es DREI (Fall E).

---

## Die drei TBD-Elemente — und was der Engine fehlt

Reihenfolge nach Bedeutung für den Market Maker:

1. **Muster** — M/W, Rises/Drops, Umkehrungen, Konsolidierungen. Zweck: Trader am
   ersten Peak in die falsche Richtung locken, dann schnell drehen.
2. **Timing** — valide M/W nur in den **Gap-Zeiten und Session-Wechseln** (CME-Zeiten,
   New York). **Dead Zone 17:00–20:00 NY**: MM offline, keine Trades.
3. **Levels** — aggressive Bursts mit Vektorvolumen; Drei-Level-/Drei-Tage-Zyklus;
   als objektive Niveaus ausschließlich HOW/LOW und HOD/LOD.

Alle drei müssen zusammenpassen. Muster ohne Timing oder ohne drei fertige Levels
= meist eine MM-Falle.

**Stand der Engine:** Muster ✓ (M/W + BCR) · Levels ✓ (Stufenzähler + HOW/LOW/HOD/LOD
als Roadblock) · **Timing FEHLT VOLLSTÄNDIG.** Die Engine prüft um 03:00 nachts
dieselben Bedingungen wie zum US-Open. Wichtig: Das ist NICHT der im Juni verworfene
Stunden-Filter (reines Data-Mining), sondern kausal begründet (MM-Übergabe) — genau
das Kriterium, das Wookie selbst für legitime Zeitfilter aufgestellt hat.

**Arbeitsteilung laut Wookie:** Das **Timing steuert die Entries**, die **Stufen sagen,
WO man nach M/W sucht.**

---

## ABGELEITETE ZYKLUS-REGELN (gültig über alle drei Fälle)

1. **Eine Stufe endet an der SVC** — Rejection-Kerze mit Docht ≳50% gegen die
   Laufrichtung, Vektorvolumen typisch (auf 1h praktisch immer). **Nicht** an einer EMA.
2. **Board Meeting** = der Rücklauf zur 50er nach dem Stufenende.
3. **Folgestufe** = bricht das Extrem der Vorstufe.
4. Die **200er ist bei Stufe 1 das Ziel, wenn sie in Laufrichtung liegt** — sie ist
   nicht die Definition. (Abwärts im Mai-Fall: ja. Aufwärts: 200er lag hinter dem
   Preis, Stufe endete trotzdem sauber an der SVC.)
5. **P1 ist der Trap, nicht die Erschöpfung** — hat oft KEINE SVC-Signatur
   (03.08: Docht 46% · 08.05: Vol 1,23× · 06.05 4h: Railroad ohne Docht).
   Die Volumen-Signatur gehört zu P3.
6. **Reversal-Kerzen sind nicht nur SVC.** Railroad Tracks (zwei gegenläufige
   Vektorkerzen, die zweite nimmt die erste zurück) sind mechanisch dasselbe:
   gefangenes Volumen am Extrem — nur über zwei Kerzen statt über einen Docht.
   Häufig auf der nächsttieferen Ebene doch als SVC sichtbar.
7. **Alle Timeframes scannen, dann über Confluence filtern.** Auf 1h gibt es fast
   an jedem Stufenende eine SVC — gültig ist sie nur, wenn 4h oder 1D ebenfalls
   ein Reversal zeigen. Dabei muss auf 1h **zurückgeschaut** werden, weil die
   4h-Kerze zu dem Zeitpunkt oft noch nicht fertig ist.
8. **Fraktal:** eine 4h-Stufe = drei 1h-Stufen. Kind-Stufe-3 = Eltern-P3 = neues
   Kind-P1. Danach bildet das Kind ein M/W — nicht immer bilderbuchmäßig.
9. Es gibt auch **V-Tops / V-Bottoms** statt M/W.
10. P1 bleibt **fest** für den ganzen Zyklus; Reversal-M/W erst nach drei Stufen;
    Failsafe: Close jenseits P1 vor L3 → Zyklus ungültig.

---

## Meine Fehler in dieser Analyse (zur Vermeidung von Wiederholung)

- Die Stufe-1-Kette (50er → 200er → Abweisung → Retest) auf **alle** Stufen
  angewendet. L2 zielt auf 800er/unrecovered Vektor, L3 ist choppy + SVC.
- Den 50er-Rücklauf als Stufenende verbucht — er ist **P2** der Formation.
- Ein TBD-Zitat über **TP-Ziele** als Zähl-Kriterium missbraucht und daraus
  fälschlich eine „Mindest-Separation der EMAs" abgeleitet. Gibt es nicht.
- Datum falsch gelesen (11.8. statt 11.5.) und daraufhin eine Nicht-Übereinstimmung
  behauptet, die es nie gab. **Monat und Jahr immer gegenprüfen.**

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
