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
