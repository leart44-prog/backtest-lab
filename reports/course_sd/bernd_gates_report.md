# Bernd-Spec-Komponenten: Einzeln gemessen (D-Serie)

Baseline D0 = beste Config der Hauptstudie (Zonen + Valuation-Gate, User-
Management). Jede Spec-Komponente einzeln als Gate, dann kombiniert. Ein
Bug im ersten Lauf (Location-Gate sah leere Zonen-Liste) wurde gefixt;
Tabelle zeigt korrigierte Zahlen.

| Config | n | WR | PF | Avg R | Trades/Wo | IS PF | OOS PF |
|---|---|---|---|---|---|---|---|
| D0 Baseline | 608 | 27.1 % | 0.87 | −0.099 | 0.94 | 0.82 | 0.92 |
| D1 + Location (5-Band, EQ raus) | 356 | 28.4 % | 0.92 | −0.057 | 0.55 | 0.91 | 0.93 |
| D2 + Trend (Pivot-Struktur) | 555 | 27.2 % | 0.87 | −0.098 | 0.86 | 0.84 | 0.90 |
| D3 + Profit-Margin (≥2R zur Gegenzone) | 491 | 27.5 % | 0.88 | −0.089 | 0.76 | 0.83 | 0.94 |
| **D4 + Arrival (sauberer Rücklauf)** | 54 | 31.5 % | **1.09** | **+0.066** | 0.11 | 0.91 | 1.34 |
| D5 alle vier | 21 | 47.6 % | 2.16 | +0.631 | 0.04 | 2.02 | 2.32 |
| D6 alle + nur Reversals | 11 | 45.5 % | 1.97 | +0.556 | 0.02 | — | — |

Zur Erinnerung aus der Hauptstudie: **HTF-Coverage (laut Spec „wichtigste
Regel") verschlechterte das Ergebnis** (PF 0.78 vs 0.81 Baseline, nach
Lookahead-Fix).

## Komponenten-Ranking (gemessen, nicht behauptet)

1. **Arrival: stärkste Einzelkomponente** (+0.165 Avg R, einziges positives
   Einzel-Gate). Deckt sich mit der Kurs-Intuition „sauberer, impulsiver
   Rücklauf" — und ist zugleich der restriktivste Filter (−91 % der Trades).
2. **Location: moderater echter Beitrag** (+0.042 Avg R, halbiert Trades).
   Equilibrium-Ausschluss wirkt.
3. **Profit-Margin: minimal** (+0.010).
4. **Trend (Pivot-Struktur): kein messbarer Beitrag** (−0.001).
5. **Coverage: negativ** (aus Hauptstudie).

Die Spec-Gewichtung ist damit empirisch invertiert: Die als am wichtigsten
deklarierte Regel (Covered) ist die einzige schädliche; die am weitesten
hinten stehende (Arrival, §5.5) ist die stärkste.

## Statistische Ehrlichkeit zu D5/D6

PF 2.16 bei n=21 über 13 Jahre sieht spektakulär aus, ist aber statistisch
leer: t ≈ 1.9 vor Multiple-Testing-Korrektur (7 Zellen), danach nicht
signifikant. 0.04 Trades/Woche = ~2 Trades/Jahr — als Strategie nicht
handelbar und live in vertretbarer Zeit nicht validierbar. Der Sprung von
PF 1.22 (Buglauf, n=44) auf 2.16 (Fixlauf, n=21) zeigt die Instabilität
kleiner Stichproben. **D5 ist ein Hinweis auf Richtung, kein Edge-Beleg.**

## Konsequenz für den Indikator (Pine-Änderungen, evidenzbasiert)

1. **NEU: Arrival-Qualifier** (0–2 Punkte, stärkste Komponente):
   sauberer Rücklauf = Preis kam ≥ 0.75 Zonenhöhen von der Proximal-Linie
   innerhalb ≤ 8 Bars, ohne dass unterwegs eine Gegenzone entstand.
2. **Location verschärfen:** Equilibrium hart ausschliessen (bisher: EQ mit
   Trend-Tiebreak erlaubt).
3. **Coverage-Gewicht von +2 auf 0 (nur Anzeige):** Der ★-Marker bleibt
   informativ, fliesst aber nicht mehr in Score/Tradeability — gemessen
   schadet die Regel.
4. **Formations-Gewicht:** DBD −1 Punkt (konsistent schlechteste Formation),
   Reversals (DBR/RBD) +1 bei aktivem Valuation-Extrem.
5. Trend-Gate optional lassen (kein messbarer Beitrag, aber unschädlich).
