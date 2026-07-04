# Sektor-Selektions-Framework — Komponenten-Test (KORRIGIERTE ZAHLEN)

**Wichtig:** Am 2026-07-02 wurde in allen früheren Sektor-Läufen ein
Lookahead-Bug gefunden (pandas-3.0-Zeiteinheiten-Mismatch: der Rank-Lookup
lieferte still die Sektor-Rangliste vom LETZTEN Tag des Samples). Alle
Sektor-Zahlen vor diesem Datum sind ungültig. Dieses Dokument enthält
ausschliesslich korrigierte Resultate.

## Korrigierte Basis-Fakten (B1 High-Breakout, TP 3R, extON, 2013–2018)

| Konfiguration | n | PF | Avg R |
|---|---|---|---|
| Ohne Sektorfilter | 4925 | 1.94 | +0.543 |
| 63d-Rank Top 3 | 2105 | 2.12 | +0.629 |
| 63d-Rank Top 5 | 2709 | 2.09 | +0.616 |
| 63d-Rank Top 8 | 3190 | 2.15 | +0.639 |
| 6M-Rank Top 5 (beste Zelle) | 2393 | 2.25 | +0.681 |
| RS > Markt (Blend) | 2178 | 2.16 | +0.644 |

**Ehrliche Lesart:** Der Sektorfilter bringt real **+0.07 bis +0.14 R/Trade**
(nicht +0.30 wie die fehlerhaften Zahlen suggerierten). Die Strenge (Top 3
vs 5 vs 8) und der Lookback (3M vs 6M vs Blend) liegen **innerhalb des
Rauschens** (PF 2.05–2.25). Es gibt KEINEN belastbaren Strenge-Gradienten.

## Komponenten-Test (auf 63d/Top3-Basis)

| Komponente | n | PF | Avg R | Urteil |
|---|---|---|---|---|
| BASE (63d Top 3) | 2105 | 2.12 | +0.629 | Referenz |
| + RS-Linie vs Markt (über 20d-MA) | 1962 | 2.19 | +0.659 | leichtes Plus |
| + Breadth ≥ 60 % über 50-SMA | 2028 | 2.09 | +0.615 | **kein Mehrwert** |
| Nur LEADING (Top 3 auf 63d UND 21d) | 1662 | 2.17 | +0.651 | ≈ BASE |
| Nur IMPROVING (Top 3 auf 21d, nicht 63d) | 2233 | **1.75** | +0.456 | **klar schlechter** |
| IMPROVING ∪ LEADING | 2875 | 1.97 | +0.558 | verwässert |

**Der einzige klare Komponenten-Befund:** Früh-Rotation jagen (IMPROVING —
Sektoren, die nur auf 1 Monat heiss sind) ist **messbar schlechter** als
etablierte Stärke (−0.17 R/Trade vs BASE). Breadth-Bestätigung bringt nichts.
RS-Linie ist ein mildes Plus, kein Muss.

## Das Framework (final, evidenz-kalibriert)

**Stufe 1 — Ranking (Pflicht):** 63-Tage-Return der 11 Sektoren (live: SPDR-
ETFs XLK XLV XLF XLY XLP XLE XLI XLB XLU XLRE XLC). **Top 5 handelbar.**
Wöchentlich aktualisieren. Erwarteter Effekt: ~+0.1 R/Trade, PF +0.15–0.3.
Top 3 ist NICHT messbar besser als Top 5 — nimm die Breite.

**Stufe 2 — Persistenz-Check (Pflicht):** Sektor muss auch auf 126 Tage in
der oberen Hälfte (Rang ≤ 5) stehen. Zweck: schliesst reine 1-Monats-
Rotationen aus (IMPROVING-Befund: −0.17 R). Kein Nachjagen von Sektoren,
die nur wenige Wochen heiss sind.

**Stufe 3 — RS-Linien-Check (optional):** Sektor-ETF ÷ SPY über dem eigenen
20-Tage-Schnitt. Kleines Plus (+0.03 R), als Tiebreak bei zu vielen Signalen.

**Explizit NICHT im Framework:** Breadth-Schwellen (kein Mehrwert gemessen),
Top-3-Verengung (Rauschen), 1-Monats-Lookbacks als Hauptkriterium
(instabiler: Turnover 2.3–3.0 Sets/Monat vs 1.1–1.5 bei 3M/6M).

**Regime-Interaktion:** In 2015/2018 verlieren ALLE Sektor-Varianten
(beste Zelle 2015: −0.03). Der Sektorfilter ersetzt den Markt-Regime-Filter
nicht — beide Gates bleiben Pflicht.

## Wochenroutine (10 Min, Freitag nach US-Close)

1. 63d- und 126d-Return der 11 Sektor-ETFs ranken.
2. Handelbar = Rang ≤ 5 auf BEIDEN Horizonten.
3. Optional bei Signal-Überschuss: RS-Linie als Tiebreak.
4. Watchlist ausschliesslich aus diesen Sektoren.
