# Stock-Selection A/B/C-Test — MP-1 Swing-Setups auf S&P-500-Aktien

**Frage:** Bringt die Momentum-Leadership-Selektion (Kern der MP-1-These) messbaren Edge,
wenn Setups, Regime-Filter und Kosten konstant gehalten werden?

## Daten & Design

- **Daten:** S&P 500, alle ~500 Aktien, daily OHLCV **mit Volumen**, Feb 2013 – Feb 2018
  (Kaggle-Mirror via GitHub; Yahoo & Co. sind von der Egress-Policy blockiert).
- **Ranking:** Monatsende, 6-Monats-Momentum (126-Tage-Return, letzte 5 Tage ausgelassen),
  Quintile. Rank von Monat M gilt in Monat M+1 — kein Lookahead.
- **Gruppen:** Q1 = Leaders (Top-20 %), Q3 = Mittelfeld, Q5 = Laggards.
- **Setups:** identisch für alle Gruppen — S1 SMA-Reclaim, S2 Cup-and-Handle,
  S3 EMA-Pullback, S5 Washout, alle mit echter Volumen-Bestätigung.
- **Regime-Filter:** aus ES-Futures (Repo-Daten). **Kosten:** 10 bps round-trip.
- **Bekannte Verzerrungen:** Survivorship (Konstituenten per Feb 2018) wirkt auf alle
  drei Gruppen gleich — der *relative* Vergleich bleibt gültig. Nur 5 Jahre, überwiegend
  Bull-Markt.

## Kernresultat

| Gruppe | n | Win Rate | PF | Avg R |
|---|---|---|---|---|
| **Q1 Leaders** | 3571 | 40.6 % | **1.07** | **+0.037** |
| Q3 Mittelfeld | 2986 | 40.2 % | 1.02 | +0.013 |
| Q5 Laggards | 1687 | 36.9 % | **0.95** | **−0.032** |

**Monotoner Gradient Q1 > Q3 > Q5** — und zwar auch *innerhalb* jedes Setups:

| Setup | Q1 PF | Q3 PF | Q5 PF |
|---|---|---|---|
| S2 Cup-and-Handle | **2.01** | 1.33 | 1.10 |
| S3 EMA-Pullback | 1.05 | 1.01 | 0.93 |

Die Selektions-These ist also qualitativ bestätigt: dieselben Setups funktionieren
auf Momentum-Leadern besser als auf Nachzüglern.

## Aber: Signifikanz und Grösse

- **t-Statistik Q1 vs Q5: 1.38** (p ≈ 0.17) — statistisch **nicht signifikant** auf
  üblichem Niveau; wegen Korrelation der Trades (gleiche Markttage) eher noch schwächer.
- Der Gesamt-Edge der Leaders (PF 1.07 nach Kosten) ist **dünn** und jahresweise
  instabil: 2015 PF 0.62, 2017 PF 1.38.
- **Die Ausnahme ist S2 auf Leaders: PF 2.01, Avg R +0.37, n=98** (~2 Trades/Monat
  über 500 Aktien). Der Quintil-Gradient von S2 (2.01→1.33→1.10) stützt, dass das
  kein reiner Zufall ist — aber n=98 über 5 Bull-Jahre ist zu wenig für eine
  Live-Freigabe ohne Bestätigung auf einer zweiten Periode.

## Fazit

1. **Ja, die Stock-Selection ist backtestbar und der Selektions-Effekt existiert** —
   Richtung wie von der MP-1-These vorhergesagt, konsistent über Setups.
2. Der Effekt ist auf diesem Sample **klein und nicht signifikant**; tragfähig ist am
   ehesten die Kombination **Cup-and-Handle-Breakout × Momentum-Leader** (S2×Q1).
3. Nächster Validierungsschritt: gleiche Pipeline auf einer zweiten, unabhängigen
   Periode (2018–2026) — dafür braucht es eine offene Datenquelle oder gelockerte
   Netzwerk-Policy.
