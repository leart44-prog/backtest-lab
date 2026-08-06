# S&D Zones [v4] — Backtest im gleichen Umfang wie die Course-Method-Studie

**Setup identisch zur C-Serie** (40 Instrumente: FX Majors/Crosses, Indizes,
Metalle, Energien · 4H · 2013–2026 · ehrliche Fills, Same-Bar-SL = −1R,
Kosten+Kommission · Management: Limit am Proximal, SL 25 % hinter Distal,
TP 2.5R, frisch oder 1 Touch ≤ 25 %). **Nur der Zonen-Detektor wurde
getauscht** — Unterschiede sind kausal dem Detektor zuzuordnen.

Port-Hinweise: Pine `ta.atr` = Wilder-RMA (exakt nachgebildet); Impulse via
Body > 1×ATR mit Wick-Filter bzw. 2-Kerzen-Variante (1.4×ATR); Base = Body
< 0.5×ATR ODER Body/Range < 0.5; Distal = absolutes Extrem aus Impuls+Base;
Preferred-Proximal = Base-Body-Extrem. Abweichung dokumentiert: v4s
„Delete on Deep Wick ≥ 25 % hinter Distal" fällt praktisch mit unserem SL
zusammen (Trade wird gestoppt); für unbehandelte Zonen mitigiert die Engine
nur bei Close hinter Distal.

## Ergebnisse

| Config | n | WR | PF | Avg R | Trades/Wo | IS PF | OOS PF |
|---|---|---|---|---|---|---|---|
| V1 BASE (Zonen pur) | 29'895 | 26.2 % | 0.84 | −0.123 | 43.7 | 0.84 | 0.83 |
| V2 + Valuation | 810 | 26.2 % | **0.81** | −0.145 | 1.19 | 0.73 | 0.89 |
| V3 Valuation + nur frisch | 680 | 27.4 % | 0.86 | −0.107 | 1.00 | 0.80 | 0.92 |
| V4 Valuation + Arrival | 43 | 30.2 % | 0.96 | −0.029 | 0.07 | 0.54 | 2.12 |

Referenz Course-Method: BASE 0.81 · +VAL 0.87 · VAL+frisch 0.88 ·
VAL+Arrival 1.09 (n=54).

## Befunde

1. **Beide Detektoren sind auf Basis-Ebene gleich (schlecht):** v4 PF 0.84 vs
   Course 0.81 bei fast identischer Trade-Zahl (~30'000). Die unterschiedliche
   Konstruktions-Logik (ATR/Wick vs Body%-Range) ändert am Kernbefund nichts.
2. **Der Valuation-Effekt ist beim v4-Detektor NICHT reproduzierbar.** Auf
   Course-Zonen verbesserte das Gate PF 0.81 → 0.87; auf v4-Zonen
   verschlechtert es (0.84 → 0.81, IS sogar 0.73). Erst mit Frische-Zwang
   erreicht v4 0.86. **Damit ist der Valuation-Vorteil detektor-abhängig und
   schwächer generalisierbar als gedacht** — ein wichtiger Dämpfer für die
   frühere Einschätzung „bester Filter".
3. **Klassen-Detail (V2):** Der Valuation-Filter funktioniert bei v4 nur auf
   FX-Crosses ordentlich (PF 0.90); auf Metallen ist er katastrophal
   (PF 0.08, n=34 — Valuation-Extreme + v4-Zonen auf Metallen fingen die
   2024er-Trendläufe als Gegenposition). Kleine n, aber die Richtung ist
   deutlich.
4. **Formations-Muster bestätigt sich teilweise:** DBR bleibt auch bei v4
   die beste Formation unter Valuation (PF 0.97), RBD mit Frische bei 1.00.
   RBR + Valuation bleibt schwach (0.71–0.72) — konsistent mit der
   Course-Studie („Continuation-Long bei Unterbewertung widerspricht sich").
5. **V4+Arrival:** n=43, IS 0.54 / OOS 2.12 — der wilde Split zeigt reine
   Kleinstichproben-Varianz. Kein Beleg.

## Fazit

Der v4-Detektor ist weder besser noch schlechter als die Course-Methode —
**beide finden Zonen ohne eigenständigen Edge**. Wichtigste neue Erkenntnis
ist negativ-methodisch: Der Valuation-Vorteil aus der C-Serie überträgt sich
nicht auf einen anderen Zonen-Detektor und ist damit fragiler als bisher
kommuniziert. Was detektor-übergreifend stabil bleibt: DBR/Reversal >
Continuation unter Valuation-Bedingungen, und RBR+undervalued als
schlechteste Kombination.
