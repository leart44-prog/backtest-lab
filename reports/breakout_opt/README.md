# Breakout-Strategie: TP/SL-Optimierung + VIX-Sizing

**Entries:** S2 Cup-and-Handle-Breakout auf Momentum-Leaders (Q1+Q2), n=397,
S&P-500-Aktien 2013–2018, 10 bps Kosten im Entry. Engine mit Post-Audit-Fixes
(Stop-vor-Target, Same-Bar-BE-Regel). Grid a priori deklariert, alle Zellen
berichtet.

## TP × SL Grid (fix 0.5 % Risiko/Trade)

| Zelle (SL \| TP) | n | WR | Avg R | PF | Max DD | CAGR | Ø Hold |
|---|---|---|---|---|---|---|---|
| **HL−0.5A \| 2R** | 397 | 43 % | +0.267 | 1.47 | 22.0 % | 12.4 % | 7.7 d |
| **HL−0.5A \| 3R** (Baseline) | 397 | 38 % | +0.457 | 1.75 | 23.3 % | 22.2 % | 10.5 d |
| **HL−0.5A \| 4R** | 397 | 35 % | +0.586 | 1.91 | 22.1 % | 29.2 % | 12.9 d |
| HL \| 2R | 397 | 43 % | +0.267 | 1.47 | 19.7 % | 12.4 % | |
| HL \| 3R | 397 | 34 % | +0.301 | 1.45 | 25.5 % | 14.0 % | |
| HL \| 4R | 397 | 32 % | +0.482 | 1.71 | 21.0 % | 23.4 % | |
| E−1.0A \| 2R | 397 | 35 % | +0.065 | 1.10 | 16.0 % | 2.7 % | |
| E−1.0A \| 3R | 397 | 30 % | +0.189 | 1.27 | 20.9 % | 8.4 % | |
| E−1.0A \| 4R | 397 | 26 % | +0.304 | 1.41 | 24.4 % | 14.0 % | |
| E−1.5A \| 2R | 397 | 39 % | +0.179 | 1.29 | 17.9 % | 8.1 % | |
| E−1.5A \| 3R | 397 | 32 % | +0.255 | 1.37 | 23.6 % | 11.6 % | |
| E−1.5A \| 4R | 397 | 28 % | +0.378 | 1.52 | 25.5 % | 17.8 % | |
| HL−0.5A \| 3R + 50 % Partial @1R | 397 | 58 % | +0.246 | 1.59 | 15.1 % | 11.5 % | |

Legende: HL = Handle-Low (Struktur-Stop), A = ATR14 am Entry, E = Entry-Preis.

**Muster (beide monoton, das spricht gegen Zufall):**
1. **SL:** Struktur-Stop (HL−0.5A) schlägt jeden ATR-Abstand vom Entry — in
   jeder TP-Spalte. Enge Entry-relative Stops (E−1.0A) werden vom normalen
   Breakout-Retest ausgestoppt, bevor der Move kommt.
2. **TP:** Breiter = besser (2R→3R→4R steigt Avg R monoton). Die
   Gewinnverteilung von Breakouts ist rechtslastig.
3. **HL ohne Puffer** ist schlechter als HL−0.5A: der halbe ATR Puffer
   verhindert Stop-Runs knapp unter dem Handle-Low.
4. **Partial @1R:** Win-Rate 58 % und kleinster DD (15 %), aber fast halbierte
   Expectancy — bestätigt den Befund der Management-Studie.

## VIX-Sizing (VIX-Close des Vortags, kein Lookahead)

| Zelle | Sizing | Ø Risk | CAGR | Max DD | Ret/DD | Sharpe |
|---|---|---|---|---|---|---|
| HL−0.5A\|3R | Z1 fix 0.5 % | 0.500 % | 22.2 % | 23.3 % | 6.16 | 1.75 |
| HL−0.5A\|3R | Z2 invers 17/VIX | 0.678 % | 32.8 % | 27.6 % | 9.14 | 1.80 |
| HL−0.5A\|3R | Z3 gestuft | 0.708 % | 32.3 % | 29.9 % | 8.23 | 1.73 |
| HL−0.5A\|4R | Z1 fix 0.5 % | 0.500 % | 29.2 % | 22.1 % | 9.57 | 1.89 |
| HL−0.5A\|4R | Z2 invers 17/VIX | 0.678 % | 42.2 % | 26.4 % | 14.24 | 1.90 |
| HL−0.5A\|4R | Z3 gestuft | 0.708 % | 41.9 % | 29.5 % | 12.63 | 1.84 |

**Leverage-Normalisierung (kritisch!):** 2013–2018 war eine Low-VIX-Ära; die
inverse Formel ergibt Ø 0.68 % statt 0.5 % Risiko. Der CAGR-Sprung ist also
grösstenteils **mehr Hebel, nicht besseres Timing.** Auf gleiches Ø-Risiko
normiert:

| Sizing (HL−0.5A\|4R) | Ø Risk | CAGR | Max DD | Ret/DD |
|---|---|---|---|---|
| Z1 fix | 0.500 % | 29.2 % | 22.1 % | 9.57 |
| Z2 roh | 0.678 % | 42.2 % | 26.4 % | 14.24 |
| **Z2 normiert** | **0.500 %** | **29.9 %** | **20.2 %** | **10.87 (+14 %)** |

Der echte Timing-Effekt von VIX-Sizing: **gleicher Ertrag bei ~2 pp weniger
Drawdown** (Ret/DD +14–19 %). Real, aber moderat.

## Empfehlung

- **SL: Struktur (Handle-Low − 0.5×ATR).** Robusteste Zeile, in allen Spalten.
- **TP: 3R als Arbeitspunkt.** 4R ist im Sample besser, liegt aber am Rand des
  Grids (keine getestete Zelle darüber) — die 3R↔4R-Nachbarschaft ist konsistent,
  also 3R konservativ, 4R legitim für Risikofreudigere.
- **VIX-Sizing: ja, aber als Risiko-Bremse, nicht als Hebel.** Formel
  0.5 % × (17/VIX), Cap bei 0.75 % (nicht 1 %), Floor 0.25 %. So bekommst du den
  Drawdown-Schutz ohne den versteckten Leverage-Anstieg.

## Grenzen

- n=397, 5 Jahre, praktisch nur Bull/Chop-Regime, Survivorship-Bias des
  Datasets (Konstituenten per Feb 2018), endet vor Feb-2018-Vol-Schock (nur
  Aug-2015 und Anfang-2018 als High-VIX-Fenster im Sample).
- 13 Zellen + 6 Sizing-Läufe = Multiple-Testing; die Aussagen stützen sich
  deshalb auf monotone Muster (SL-Zeilen, TP-Spalten), nicht auf einzelne
  Best-Zellen.
- VIX-Sizing wurde nur in einer Ära getestet, in der hohe VIX-Werte selten
  waren; der eigentliche Nutzen (2020, 2022) liegt ausserhalb des Samples.
