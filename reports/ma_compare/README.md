# SMA vs EMA für Reversals — paired Vergleich

**Test A — Pullback-Reversal im Trend** (Aktien, Q1+Q2-Leaders, 2013–2018,
Tag der MA + Close-Reclaim, Stop unter Pullback-Low, TP 2R):

| MA | n | WR | PF | Avg R |
|---|---|---|---|---|
| EMA10 | 6553 | 34.4 % | 1.05 | +0.032 |
| SMA10 | 5014 | 34.5 % | 1.05 | +0.035 |
| EMA20 | 6072 | 35.7 % | 1.11 | +0.072 |
| SMA20 | 5156 | 35.2 % | 1.09 | +0.057 |

**Test B — Trend-Reversal per MA-Cross** (Index-Futures daily, 2013–2026,
long-only, Cross-up rein / Cross-down raus, Kosten drin):

| Länge | SMA PF | EMA PF | SMA Ø-Trade | EMA Ø-Trade |
|---|---|---|---|---|
| 10 | 1.27 | 1.22 | +0.19 % | +0.16 % |
| 20 | 1.36 | 1.26 | +0.30 % | +0.21 % |
| 50 | 1.64 | 1.51 | +0.55 % | +0.45 % |
| 100 | 1.93 | 1.78 | +0.88 % | +0.73 % |
| 200 | 2.38 | 2.36 | +1.47 % | +1.40 % |

## Befunde

1. **Der SMA/EMA-Unterschied ist zweite Ordnung.** Bei Pullback-Tags liegt
   EMA20 hauchdünn vorn (+0.015R vs SMA20 — statistisch nicht signifikant bei
   Trade-Std ~1.2). Bei Cross-Reversals liegt SMA auf jeder Länge 10–100
   leicht vorn (weniger Whipsaws), bei 200 sind beide identisch.
2. **Die Periodenlänge ist erste Ordnung.** PF steigt monoton von 10 → 200
   (1.2 → 2.4) — um Faktoren grösser als jeder SMA/EMA-Effekt.
3. EMA erzeugt ~20–25 % mehr Pullback-Signale (liegt näher am Preis),
   bei praktisch gleicher Qualität pro Signal.

## Empfehlung

Die Frage „SMA oder EMA" ist für Reversals empirisch fast irrelevant —
entscheidend ist die Länge. Wähle nach Funktion, bleib dann konsistent:
- Pullback-Entries im Trend: EMA20 (mehr Signale, minimal beste Zelle,
  Standard im Playbook).
- Regime-/Reversal-Erkennung: SMA (50/200) — marginal robuster gegen
  Whipsaws und die akademische Referenz-Definition.
