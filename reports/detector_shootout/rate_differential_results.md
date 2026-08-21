# Paarspezifische Zinsdifferentiale vs. Zonen-Reversal-Config

Frage des Users: Zinsen der Basiswaehrung vs. Quotewaehrung je Paar.
Daten: backtest/policy_rates.py (dokumentierte Leitzins-Historie aller 8
Zentralbanken 2003-2026, monatsgenau, konservativ Monat+1 wirksam; NZ
exakt aus TradingView-Eventserie, US-Endstand 3.75% verifiziert).
Vorab deklariert: M1 = |Differential| am Entry, Schwelle 1.0%. M2 =
|12-Monats-Aenderung des Differentials|, Schwelle 0.5%. M3 = beides.
Trades: Dukascopy-FX, age500, ehrliche Fills, Kosten.

## REVERSALS (n=149)

| Split | Zelle | n | OER | PF |
|---|---|---|---|---|
| M1 Niveau | klein (<1%) | 48 | +0.15 | 1.21 |
| M1 Niveau | gross (>=1%) | 101 | +0.13 | 1.19 |
| **M2 Bewegung** | **stabil (<0.5%/12M)** | **71** | **+0.30** | **1.47** |
| **M2 Bewegung** | **in Bewegung (>=0.5%)** | **76** | **-0.03** | **0.95** |
| M3 beides | komprimiert & stabil | 33 | +0.35 | 1.57 |
| M3 | Rest | 116 | +0.07 | 1.11 |

M3-gut in UNGESEHENEN Jahren (<2013): PF 1.96 (n=9, zu klein fuer
Beweiskraft, Richtung stimmt); Rest ungesehen: 0.91.

## VAL_FRESH (n=213): keine Trennung

M1 sogar invers (0.76 vs 1.10), M2 flach (0.99 vs 0.95). Der
Differential-Effekt ist reversal-spezifisch — oder Rauschen bei kleinem n.

## Befund

1. Das NIVEAU des Differentials (Carry gross/klein) trennt nichts.
2. Die BEWEGUNG des Differentials trennt auf der Reversal-Config klar:
   Edge, wenn die Zinsdifferenz seit ~1 Jahr steht; kein Edge, waehrend
   sie neu bepreist wird. Das ist die paar-genaue Version des
   Fed-Phasen-Befunds (geparkte Zinsen -> Range -> Reversals).
3. Die Fed-Phasen-Regel (Hold-tief PF 1.95 / Hold-hoch 0.28) bleibt der
   staerkere und einfachere Filter; das Differential bestaetigt den
   Mechanismus, ersetzt sie aber nicht (Hold-hoch-Versagen bleibt vom
   Differential unerklaert).
4. Vorsicht: Buckets mit n=33-76; Effektrichtungen konsistent, aber
   keine Praezision. Rekonstruierte Zinshistorie monatsgenau.

## Nachtrag: Differential als RICHTUNGS-Filter (User-Idee)

Idee des Users: nur die Seite handeln, die das Differential stuetzt
(Bsp.: CHF-Zins ueber EUR -> nur EURCHF-Shorts an Supply-Zonen).
Deklariert: A = Richtung Hochzins-Waehrung (Niveau-Vorzeichen),
B = Richtung der 12M-Differentialbewegung. REVERSALS age500, Dukascopy.

| Filter | Zelle | n | OER | PF | UNGESEHEN (<2013) | 2013+ |
|---|---|---|---|---|---|---|
| A Niveau | KONFORM (mit Hochzins) | 90 | -0.04 | 0.94 | 0.78 (41) | 1.10 (49) |
| A Niveau | **DAGEGEN (gegen Hochzins)** | **56** | **+0.42** | **1.69** | **1.62 (20)** | **1.72 (36)** |
| B Bewegung | konform (mit Bewegung) | 75 | +0.21 | 1.32 | 1.15 (34) | 1.48 (41) |
| B Bewegung | dagegen | 37 | +0.01 | 1.01 | 0.94 (18) | 1.07 (19) |
| Kombi (gegen Niveau, mit Bewegung) | | 26 | +0.33 | 1.52 | 1.21 (9) | 1.71 (17) |

Befund: Die Idee wirkt — aber INVERTIERT. Zonen-Reversals GEGEN die
Hochzins-Waehrung sind die erste Zelle der gesamten Session, die in
BEIDEN Aeren haelt (1.62 / 1.72). Mechanik plausibel: das System ist
Mean-Reversion; die Carry-Seite ist die gedehnte Seite; an frischen
Zonen mit Valuation-Extrem schnappt der Preis gegen sie zurueck.
Im User-Beispiel heisst das umgekehrt zur Intuition: CHF hochverzinst
-> eher EURCHF-LONGS an Demand-Zonen.

Vorsicht: n=56 ueber 23 Jahre (~2.4 Trades/Jahr auf 28 Paaren); die
Zelle ist eine von ~8 getesteten (Inversions-Auswahl nachtraeglich);
Zinshistorie monatsgenau rekonstruiert. Stabilitaet ueber beide Aeren
ist das staerkste Argument — Frequenz und Selektionsrisiko bleiben.
