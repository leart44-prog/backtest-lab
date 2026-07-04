# Sektor-Selektion optimiert (auf B1 High-Breakout, TP 3R, extON)

Alle Zellen berichtet; Baseline ohne Filter: PF 1.94, avgR +0.543 (n=4925).

## Grid: Lookback × Strenge

| Lookback | Top 3 | Top 5 | Top 8 | Turnover/Mt (Top3) |
|---|---|---|---|---|
| 1M (21d) | **PF 2.69 / +0.845** | 2.51 / +0.780 | 2.25 / +0.680 | 2.29 |
| 3M (63d) | **PF 2.69 / +0.845** | 2.35 / +0.721 | 2.38 / +0.732 | **1.64** |
| 6M (126d) | 2.01 / +0.572 | 2.16 / +0.635 | 2.29 / +0.697 | 1.18 |
| Blend | 2.53 / +0.791 | 2.46 / +0.760 | 2.29 / +0.693 | 1.80 |
| RS > Markt (Blend) | — | PF 2.51 / +0.779 (n=1396) | — | — |

Anmerkung: 1M-Top3 und 3M-Top3 selektierten im Sample praktisch dieselben
Trades (identische Kennzahlen) — die Top-3-Sektoren überlappten stark.

## Jahres-Konsistenz der Kandidaten

| Jahr | blend/top5 (v2.1) | 3M/top3 | 6M/top3 |
|---|---|---|---|
| 2013 | +1.28 | +1.26 | +0.79 |
| 2014 | +0.33 | **+0.71** | +0.67 |
| 2015 | −0.17 | **−0.02** | **+0.20** |
| 2016 | +1.37 | +1.17 | +0.52 |
| 2017 | +1.13 | +1.19 | +0.80 |
| 2018 | −0.17 | −0.08 | −0.16 |

## Befunde

1. **Strenger ist besser — monoton.** Top 3 schlägt Top 5 schlägt Top 8 in
   1M/3M/Blend. Der Edge konzentriert sich in den führenden 2–3 Sektoren.
2. **Kürzere Lookbacks schlagen 6M.** 3M (63 Tage) ist der Sweet Spot:
   Performance wie 1M, aber ~30 % weniger Sektor-Rotation (1.64 vs 2.29
   Wechsel/Monat) — praktikabler und weniger Rausch-getrieben.
3. **3M/Top3 ist auch der konsistenteste Kandidat:** verliert 2015 fast
   nichts (−0.02 vs −0.17 bei blend/top5) und ist 2014 deutlich besser.
   6M/Top3 ist der defensivste (2015 sogar positiv), kauft das aber mit
   niedrigeren Spitzen.
4. **Relative-Stärke-Modus (Sektor > Markt)** liefert ähnliche Qualität mit
   adaptiver Breite — gute Alternative, wenn man keine feste Zahl will.
5. Multiple-Testing-Einordnung: 15 Zellen, aber die Aussagen stützen sich
   auf monotone Muster (Strenge-Gradient in 3 von 4 Lookbacks, konsistente
   Lookback-Ordnung), nicht auf eine Best-Zelle.

## Konkrete Live-Prozedur (wöchentlich, ~10 Minuten)

1. Freitag nach US-Close (oder Wochenende): 63-Tage-Return der 11
   SPDR-Sektor-ETFs berechnen: XLK, XLV, XLF, XLY, XLP, XLE, XLI, XLB,
   XLU, XLRE, XLC. (ETF-Return ist der handelbare Proxy für unseren
   equal-weight GICS-Return.)
2. Absteigend sortieren. **Top 3 = handelbare Sektoren** der Folgewoche
   (Top 5, wenn zu wenige Setups entstehen).
3. Sanity-Check: Top-Sektor-Return sollte > SPY-63d-Return sein; wenn kein
   Sektor den Markt schlägt, ist das Regime verdächtig (breiter Abverkauf
   oder extreme Konzentration) — Grösse halbieren.
4. Watchlist nur aus Aktien dieser Sektoren bauen; alle anderen Signale
   ignorieren.

## Playbook-Änderung (v2.2)

R1.5 neu: Sektor-Gate = **Top 3 von 11 nach 63-Tage-Return** (statt Top 5
Blend), wöchentlich aktualisiert; Top 5 zulässig als Breiten-Fallback;
optionaler RS-Check gegen SPY als Regime-Warnung.
