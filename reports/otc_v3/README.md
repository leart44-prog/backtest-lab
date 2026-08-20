# OTC S&D Zoning v3 — Daily-Backtest (neuer Indikator + alte Valuation)

Port des neuen Pine-v5-Indikators "OTC S&D Zoning v3" (`backtest/otc_v3_zones.py`),
Settings exakt wie auf dem Chart des Users (Screenshots 2026-08-20):
Leg-in >40 % / Base ≤40 % / Leg-out >65 % Body, max. 8 Base-Kerzen,
Leg-in-first (Mode B), Absorb small (N=1.0), Stick-out ≥50 % der
Leg-out-Range, Höhe ≤1.25× Leg-out, **2-Kerzen-Leg-out AN**, Gap-Integration
(Departure + Leg-in) AN, Pivot-Integration AN (1.0× AvgRange, PivLen 5),
**Overlap: Skip if overlapping active**, **Speed-Bump-Filter AN**,
**Proximal = Preferred**, Skip 2 Kerzen, Mitigation = Close beyond Distal,
First-Touch-Protokoll (tradeable nur tests < 1), **SL 33.33 %** hinter Distal.
HTF-Layer und Action Matrix: aus (wie auf dem Chart).

Rahmen wie alle bisherigen Studien: 40 Instrumente, Daily (Resample der
4H-Daten), 2013–2026, Valuation = alter Port (ROC 10/15, Z-100, Smooth 3,
Schwellen 60/70/80, Gate liest den letzten abgeschlossenen Bar), Kosten
(Spread/Slippage im Entry, Kommission in R), IS/OOS-Split 2021-01-01.
Matrix vor dem Lauf deklariert, alle Zellen berichtet.

**6'619 First-Tests** (= Fills) übers Universum.

## A) Ehrliche Konvention (vergleichbar mit allen bisherigen Tests)

Same-Bar-Stopout = −1R, günstiger Entry-Bar-Verlauf ignoriert, SL vor TP
intrabar, 1 Position je Instrument, Kosten an.

| Zelle | n | WR | PF | ØR | Tr/Woche | IS-PF | OOS-PF |
|---|---|---|---|---|---|---|---|
| BASE · TP 1.0R | 5'729 | 43.9 % | 0.75 | −0.14 | 8.4 | 0.76 | 0.73 |
| BASE · TP 2.0R | 5'016 | 31.3 % | 0.88 | −0.09 | 7.3 | 0.90 | 0.85 |
| BASE · TP 2.5R | 4'705 | 27.1 % | 0.90 | −0.08 | 6.9 | 0.94 | 0.84 |
| VAL · TP 1.0R | 117 | 35.9 % | **0.54** | −0.30 | 0.25 | 0.57 | 0.51 |
| VAL · TP 2.0R | 117 | 22.2 % | **0.55** | −0.36 | 0.25 | 0.44 | 0.66 |
| VAL · TP 2.5R | 117 | 17.1 % | **0.50** | −0.42 | 0.25 | 0.31 | 0.69 |

Kostenlos (Diagnose): BASE|1R 0.83 · BASE|2.5R 0.97 · VAL|1R 0.56 ·
VAL|2.5R 0.55 → auch OHNE Kosten kein Edge. Same-Bar-Stopouts ~16 %
(VAL ~21 %).

## B) Pine-Ledger-Replikation (was die Tabelle auf dem Chart rechnet)

Fill am rohen Proximal, Auflösung beginnt AUF dem Fill-Bar (Same-Bar-TP
zählt als Gewinn), "Loss first" nur wenn SL+TP im selben Bar, costR = 0,
keine Positionsbegrenzung.

| Zelle | n | 1R: WR / PF | 2R: WR / PF |
|---|---|---|---|
| LEDGER BASE | 6'608 | 57.2 % / **1.34** | 36.4 % / 1.15 |
| LEDGER VAL | 122 | 54.1 % / 1.18 | 30.3 % / 0.87 |

## Befunde

1. **Die Chart-Tabelle des Indikators überzeichnet auf Daily massiv.**
   Ledger-BASE zeigt PF 1.34 (1R) — unter ehrlicher Entry-Bar-Behandlung
   bleiben davon 0.83 (kostenlos) bzw. 0.75 (mit Kosten). Fast die ganze
   Differenz ist die Same-Bar-Mehrdeutigkeit: auf einem Daily-Bar, der den
   Proximal berührt, liegt ein 1R-Ziel oft noch in derselben Kerzen-Range —
   der Ledger wertet das als Gewinn, obwohl die Intrabar-Reihenfolge
   unbekannt ist. Der Indikator-Quellcode warnt selbst davor
   ("Daily-Bars sind für Same-Bar-Entscheidungen mehrdeutig, ~36 %").
2. **Basis-Ebene: identisch mit allen bisherigen Detektoren.** PF 0.90
   (TP 2.5, ehrlich, Kosten) bzw. 0.97 kostenlos — Course 0.92, v4 0.92,
   v5 0.91. Vierte Replikation: Die Zonen-Erkennung ist nicht der Engpass.
3. **Valuation-Gate verschlechtert diesen Detektor** (PF 0.50–0.55,
   n=117, IS und OOS beide <1) — im Gegensatz zu Course/v5, wo Valuation
   auf Breakeven hob (1.00–1.05). Bei n=117 ist die Punktschätzung
   verrauscht, aber die Richtung ist über alle TP-Stufen und beide
   Teilperioden konsistent. Die Kombination aus Gap-Proximals,
   Pivot-erweiterten Distals, Overlap-Skip und SL 33.33 % setzt Entries
   und Stops anders als v5 — das Valuation-Timing passt hier nicht.
4. Frequenz der VAL-Zelle: 0.25 Trades/Woche — weit unter dem Ziel von
   2–3/Woche.

## Beispiel-Trades zum manuellen Nachprüfen (VAL, TP 2.5R)

```
CL      long  Fill 2018-11-13 @ 55.58   | SL 54.563  | TP 58.122 -> TP (+2.50R, 3 Tage)
GBPCHF  long  Fill 2019-05-21 @ 1.2818  | SL 1.2771  | TP 1.2935 -> SL (-1.04R, 1 Tag)
USDCHF  long  Fill 2020-03-05 @ 0.9475  | SL 0.94201 | TP 0.96122 -> SL (-1.02R, 1 Tag)
AUDJPY  short Fill 2022-03-24 @ 91.117  | SL 91.601  | TP 89.908 -> SAME_BAR_SL (-1.03R)
GBPJPY  long  Fill 2022-09-25 @ 150.55  | SL 148.47  | TP 155.77 -> TP (+2.49R, 1 Tag)
RTY     short Fill 2023-12-01 @ 1865.9  | SL 1901.5  | TP 1776.8 -> SL (-1.00R, 9 Tage)
```

## Konsequenz

Der neue Detektor ist sauber konstruiert (kein Repainting, klare
State-Machine), aber er ändert am Kernbefund nichts: Erster Retest einer
S/D-Zone hat auf Daily nach ehrlichen Fills keinen Edge, und die
On-Chart-Backtest-Tabelle ist auf Daily wegen Same-Bar-Mehrdeutigkeit
nicht belastbar (der eigene Code empfiehlt 1H/4H-Charts dafür). Die beste
bekannte Konfiguration bleibt v5-Synthese + Valuation + frisch + TP 2.5R
(PF 1.05) — der Wechsel auf OTC v3 mit diesen Settings wäre ein
Rückschritt.
