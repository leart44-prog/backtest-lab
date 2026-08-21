# 4H-Test der Gegen-Carry-Reversal-Config (v2, native 4H-Valuation)

Frage: Uebertraegt sich der Daily-Befund (Reversals gegen die
Hochzins-Waehrung, PF 1.6-2.0) auf den 4H-Chart?

Setup: `backtest/run_h4_against_carry.py`. Zwei Quellen: (a) Repo-4H
(28 FX-Paare, broker-aligned, 2013-2026, Aera-Split 2021), (b) Dukascopy
1H->4H (22:00-UTC-aligned, 21 Crosses, 2003-2026, Aera-Split 2013,
Majors-Legs nativ 4H). 8 deklarierte Zellen je Quelle (Alter {500,3000
Bars} x TP {2,2.5,3,4}), Valuation nativ auf 4H (wie der v6-Indikator
auf dem 4H-Chart; ein v1-Lauf mit Tages-Legs war ein dokumentierter
Konstruktionsfehler und wurde verworfen).

## Ergebnisse (PF; AGAINST = gegen Hochzins-Waehrung)

Lokal (2013-2026):
| Zelle | ALL | AGAINST | fr./sp. Haelfte | WITH |
|---|---|---|---|---|
| age500 tp2.5 | 0.99 | 1.21 (n=138) | 1.31 / 1.14 | 0.85 |
| age3000 tp2.5 | 0.95 | **1.26** (n=149) | 1.41 / 1.14 | 0.76 |
| age3000 tp4 | 0.91 | 1.08 (n=147) | 1.04 / 1.11 | 0.82 |

Dukascopy (2003-2026):
| Zelle | ALL | AGAINST | vor 2013 / danach | WITH |
|---|---|---|---|---|
| age500 tp2.5 | 0.90 | 1.03 (n=238) | **1.50 / 0.82** | 0.84 |
| age500 tp4 | 1.02 | 1.15 (n=234) | 1.37 / 1.03 | 0.96 |
| age3000 tp2.5 | 0.84 | 0.97 (n=252) | 1.31 / 0.81 | 0.78 |

Verifikation: unabhaengiger First-Passage-Check der Trades — Ausgaenge
(SL/TP/Same-Bar) stimmen ueberein; R-Abweichungen ausschliesslich in
Kommissionshoehe (engine netto vs. Checker brutto).

## Befunde

1. **Die RICHTUNG des Carry-Splits repliziert perfekt: In allen 16
   Zellen ist AGAINST > WITH** (WITH durchweg 0.76-0.96). Der
   Mechanismus (Zonen-Reversals funktionieren gegen die gedehnte
   Carry-Seite) ist damit ueber Timeframes und Quellen bestaetigt.
2. **Die HOEHE des Edges ueberlebt den Wechsel auf 4H nicht.**
   AGAINST liegt auf 4H bei PF ~1.0-1.26 statt 1.6-2.0 (Daily) — nach
   Kosten um Breakeven. 4H-Zonen sind ~6x kleiner, Spread/Slippage
   fressen relativ mehr, und das 4H-Valuation-Gate ist ein anderes,
   schnelleres Signal.
3. **Quellen-Inkonsistenz auf 4H:** Lokal ist AGAINST in beiden
   Haelften >1, auf Dukascopy nur vor 2013 (1.2-1.5), danach 0.8-1.0.
   Ein Effekt, der im Ueberlappungszeitraum je nach Quelle/Universum
   das Vorzeichen wechselt, ist nicht handelbar.
4. Frequenz waere besser (10-18 Trades/Jahr statt 2-3), nuetzt aber
   ohne stabilen Edge nichts.

## Konsequenz

Das Konzept bleibt ein DAILY-Setup. Auf 4H ist nur die Regel "NIE mit
der Hochzins-Waehrung an Zonen handeln" belastbar (16/16 Zellen) — als
Verbots-, nicht als Einstiegsregel.
