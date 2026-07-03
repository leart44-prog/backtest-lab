# Trade-Management-Frameworks — Paired-Replay-Backtest

**Design:** Entries konstant, Management variiert. Jedes Entry-Signal wird durch
6 Management-Varianten geschickt (paired comparison) — Unterschiede sind damit
kausal dem Management zuzuschreiben.

| Variante | Regeln |
|---|---|
| M1_fix2R | Set-and-forget, TP fix 2R |
| M2_fix3R | Set-and-forget, TP fix 3R |
| M3_partial | 50 % raus bei +1R, Stop→BE, Rest auf 3R |
| M4_chandelier | BE bei +1R, dann Chandelier-Trail 3×ATR14, kein fixes TP |
| M5_mp1 | 1/3 raus bei +1.5R, Stop→BE, Rest EMA20-Trail |
| M6_time10 | TP 2R, Zwangs-Exit nach 10 Handelstagen |

Konservative Intrabar-Regel: Stop vor Target. Kosten im Entry eingerechnet.

## Welt 1 — Stocks: S2-Breakout auf Momentum-Leaders (n=397, 2013–2018)

| Variante | PF | Avg R | WR | Max DD | Ø Hold |
|---|---|---|---|---|---|
| M1_fix2R | 1.47 | +0.267 | 43 % | 22.0 % | 7.7 d |
| **M2_fix3R** | **1.75** | **+0.457** | 38 % | 23.3 % | 10.5 d |
| M3_partial | 1.59 | +0.250 | 58 % | **15.1 %** | 8.2 d |
| M4_chandelier | 1.60 | +0.253 | 53 % | 15.3 % | 6.2 d |
| M5_mp1 | 1.62 | +0.313 | 49 % | 19.8 % | 8.1 d |
| M6_time10 | 1.51 | +0.133 | 53 % | **6.8 %** | 1.5 d |

**Befund:** Der Breakout-Entry hat auf diesem Sample echten Edge (alle Varianten
positiv). Für Breakouts gewinnt **„weit laufen lassen"**: M2 (fix 3R,
set-and-forget) hat die höchste Expectancy — Breakout-Gewinne sind rechtslastig,
frühe Teilgewinne kappen genau die Trades, die das System tragen.
**M3/M4 sind die besten risiko-adjustierten Varianten** (DD ~15 % statt 23 %,
Win-Rate > 50 % = psychologisch leichter handelbar). M6 (Time-Stop) halbiert
nochmals den DD, aber kostet 70 % der Expectancy.

**Empfehlung Stocks-Framework:**
- Basis: **M2 fix 3R** wenn Fokus maximale Expectancy und DD-Toleranz ~25 %.
- Konservativ: **M3 (50 % @ 1R, BE, Rest 3R)** wenn Prop-Firm-artige DD-Limits
  oder psychologische Präferenz für Win-Rate.

## Welt 2 — S/D auf Forex + Indices + Metalle (n=5965 Fills, 2013–2026)

**Kritischer Befund zuerst:** Die erste Version der Zonen-Engine übersprang
Fills, bei denen der Retest-Bar im selben 4H-Bar auch den Stop riss.
**18.8 % aller Fills sind solche Same-Bar-Stop-Outs** — mit Limit-Orders sind
das reale −1R-Verluste. Ohne diese Korrektur zeigte die Welt PF 1.18–1.31;
**mit ehrlicher Abrechnung kippt alles ins Negative:**

| Variante | PF | Avg R |
|---|---|---|
| M1_fix2R | 0.86 | −0.097 |
| M2_fix3R | 0.89 | −0.088 |
| M3_partial | 0.81 | −0.109 |
| **M4_chandelier** | **0.88** | **−0.069** |
| M5_mp1 | 0.86 | −0.088 |
| M6_time10 | 0.86 | −0.097 |

Per Asset-Klasse (M4): Forex PF 0.83, Indices 1.03, Metalle 1.02 — nirgends
handelbar. IS/OOS (M4): 0.81 / 0.99.

**Befund:** Der S/D-First-Retest-Entry (Basis ≤ 3 ruhige Bars, impulsiver
Abgang ≥ 1.5×ATR, Trendfilter SMA300, erster Retest) hat auf 13 Jahren und
38 Instrumenten **keinen Edge**. Kein Management-Schema kann einen negativen
Entry retten — Management formt die Verteilung, erschafft aber keine Expectancy.
Innerhalb der Verlust-Welt verliert der Chandelier-Trail (M4) am wenigsten,
und die Rangfolge M4 > M2/M5 > M1/M6 > M3 ist konsistent mit der Stocks-Welt:
**Teilgewinn bei +1R (M3) ist in beiden Welten die schwächste Idee.**

## Übergreifende Erkenntnisse

1. **Management erschafft keinen Edge.** Stocks-Welt: alle 6 Varianten positiv.
   S/D-Welt: alle 6 negativ. Die Entry-Qualität dominiert.
2. **Frühe Teilgewinne (+1R) sind teuer.** In beiden Welten schneidet M3 bei
   Expectancy am schlechtesten ab; es kauft Win-Rate und niedrigeren DD gegen
   einen erheblichen Teil des Erwartungswerts.
3. **Fill-Annahmen können einen Backtest komplett fälschen.** Eine einzige
   optimistische Regel (Same-Bar-Violations überspringen) drehte PF 0.86 auf 1.31.
4. Der Time-Stop (M6) ist das effektivste DD-Kontrollwerkzeug, kostet aber am
   meisten Expectancy — sinnvoll nur für enge Prop-Firm-Limits.

## Empfohlene Frameworks (zusammengefasst)

**Stocks (Breakout):**
Entry Breakout-Close → Stop unter Konsolidierungs-Low − 0.5×ATR → fix 3R Target,
set-and-forget (aggressiv) ODER 50 % @ 1R + BE + Rest 3R (konservativ).
Kein Trailing vor +1R, keine Teilgewinne vor +1R.

**Forex/Indices/Metalle (S/D):**
**Nicht handeln wie definiert.** Der getestete S/D-Entry ist nach ehrlichen
Fills negativ. Vor jeder Management-Diskussion muss der Entry selbst
überarbeitet werden (z. B. tiefere Entry-Platzierung in der Zone, HTF-Konfluenz,
Session-Filter) — und jede Überarbeitung gehört erneut getestet, nicht angenommen.
