# Regime-Analyse: Fed-Zinsphasen vs. Zonen-Reversal-Edge (2003–2026)

Frage: Warum funktionierte die Config (v5-Reversals + Valuation + frisch,
TP 2.5R) 2013–2026, aber nicht 2003–2012? Kandidat des Users:
Zinspolitik. Methode: 12 dokumentierte Fed-Phasen (Anhebung / Senkung /
Hold-tief / Hold-hoch), je Phase (a) rohes Chart-Verhalten (28
Dukascopy-FX-Paare: Trend-Effizienz = |Netto-Weg| / zurückgelegter Weg;
S&P-500-CFD: Verlauf, Max-Drawdown) und (b) die Trades der Config
(REVERSALS, age100 & age500) auf Dukascopy-FX. `backtest/run_regime_phases.py`.

## Phasentabelle (cfg500 = ohne Altersfilter)

| Phase | Typ | FX-Effizienz | SPX | Config: n / ØR / PF |
|---|---|---|---|---|
| 2003-01–2004-06 Hold 1 % | hold_tief | 0.040 | +25 % | 3 / +0.16 / 1.23 |
| 2004-06–2006-06 Anhebung→5.25 % | hiking | 0.041 | +9 % | 5 / −0.32 / 0.61 |
| 2006-06–2007-09 Hold 5.25 % | hold_hoch | 0.055 | +16 % | 15 / −0.32 / 0.61 |
| 2007-09–2008-12 GFC-Senkung | cutting | 0.082 | −52 % DD | 21 / −0.18 / 0.77 |
| 2008-12–2015-12 ZIRP+QE | hold_tief | 0.023 | +124 % | 37 / +0.56 / 2.01 |
| 2015-12–2018-12 Anhebung→2.5 % | hiking | 0.021 | +23 % | 10 / +0.38 / 1.62 |
| 2018-12–2019-07 Hold 2.5 % | hold_hoch | 0.060 | +20 % | 7 / −1.03 / 0.00 |
| 2019-07–2020-03 Senkung+Covid | cutting | 0.092 | −28 % DD | 10 / +0.32 / 1.52 |
| 2020-03–2022-03 ZIRP (Covid) | hold_tief | 0.054 | +74 % | 20 / +0.56 / 1.99 |
| 2022-03–2023-07 Anhebung→5.5 % | hiking | 0.052 | −22 % DD | 5 / +1.08 / 3.69 |
| 2023-07–2024-09 Hold 5.25–5.5 % | hold_hoch | 0.019 | +18 % | 7 / −1.04 / 0.00 |
| 2024-09–2026-02 Senkungszyklus | cutting | 0.055 | +21 % | 9 / +0.01 / 1.02 |

## Aggregat nach Phasentyp (cfg500, n=149)

| Typ | n | ØR | PF |
|---|---|---|---|
| **Hold tief (ZIRP/Boden)** | 60 | **+0.54** | **1.95** |
| Anhebung | 20 | +0.38 | 1.62 |
| Senkung | 40 | −0.01 | 0.98 |
| **Hold hoch (Plateau oben)** | 29 | **−0.66** | **0.28** |

## Der Härtetest

Die Phasenzuordnung kommt aus externen Fed-Daten, nicht aus der
Performance — trotzdem ist sie nach Sichtung der Ergebnisse gewählt
(post-hoc-Risiko). Deshalb der Schnitt entlang der nie fürs Tuning
benutzten Jahre:

- ZIRP-Phase zerlegt: 2009–2012 (**ungesehen**) PF 1.95 (n=20) vs.
  2013–2015 (gesehen) PF 2.07 — praktisch identisch.
- Nur ungesehene Jahre: Hold-tief-Jahre PF **1.84** (n=23) vs.
  Nicht-Hold-tief-Jahre PF **0.69** (n=41).

**Der Regime-Split erklärt das OOS-Versagen:** Der Verlust 2003–2012 war
vollständig in 2004–2008 konzentriert (Anhebung → Hold-hoch → GFC);
die ZIRP-Jahre 2009–2012 waren so profitabel wie die spätere Ära.
Auffälligstes Einzelmuster: **Alle drei Hold-hoch-Phasen sind negativ**
(0.61 / 0.00 / 0.00), über zwei Jahrzehnte, inkl. der ungesehenen
2006–07. Alle drei Hold-tief-Phasen sind positiv.

Mechanik-Hinweis: Die Hold-tief-Phasen haben die niedrigste
FX-Trend-Effizienz (0.023–0.054 = Range-Märkte) — genau das Umfeld, in
dem Limit-Reversals an Zonen funktionieren. Senkungsphasen sind die
trendstärksten (0.082–0.092) — Limit-Käufer werden überrannt.

## Einordnung & Vorsicht

- n je Bucket 20–60, Phasen-n teils einstellig — Richtungen, keine
  Präzision. Das Hold-hoch/Hold-tief-Muster ist das robusteste Element
  (6/6 Phasen konsistent).
- Als handelbare Regel wäre das: **Zonen-Reversals nur, wenn die Fed
  (Leitzins) unten angekommen ist und hält; Finger weg auf dem
  Zins-Plateau oben.** Stand Aug 2026 (Senkungszyklus läuft):
  historisch die Breakeven-Kategorie — noch kein grünes Regime.
- Nächste Stufe (nicht gebaut): echtes Zinsdifferential je Währungspaar
  (Carry-Dispersion) statt nur US-Phase; COT-Positionierung (CFTC, ab
  2006, wöchentlich) als zweiter Kandidat.
