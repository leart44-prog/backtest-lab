# MP-1 Swing-Only — Backtest-Report

**Datum:** 2026-07-02 · **Daten:** Repo-Futures 4H→Daily (UTC), 2013–2026 · **Kosten:** Spread + Slippage + Kommission eingerechnet

## Wichtige Abweichungen vom Plan

1. **Yahoo Finance war nicht verfügbar** — die Egress-Policy dieser Session blockiert
   alle Finanzdaten-Hosts (Yahoo, Stooq, AlphaVantage, Tiingo). Getestet wurde auf den
   vorhandenen Index-Futures (NQ, ES, YM, RTY, DAX, NKD) als Equity-Proxy plus
   Commodities (NG, SI, HG, CL, PL, PA) als Robustheits-Kontrollgruppe.
   **Die Einzelaktien-Komponente von MP-1 (Stock-Picking, Sektor-Rotation) ist damit
   ungetestet.**
2. **Kein Volumen in den Daten** — Volumen-Bestätigung wurde durch Range-Bestätigung
   ersetzt (True Range ≥ 1.2 × ATR20 am Trigger-Tag).
3. **Scale-Ins vereinfacht** — Voll-Entry am Trigger-Close statt 40/40/20-Staffelung.

## Setups (Swing-Only, Daily-Close-Trigger, long only)

| Code | Setup | Regel-Kern |
|---|---|---|
| S1 | 50-SMA Reclaim | ≤15 Tage unter steigender SMA50, Close ≥ 1 % darüber |
| S2 | Cup-and-Handle | 25–60-Tage-Basis ≤ 20 % tief, 3–8-Tage-Handle oberes Drittel, Breakout |
| S3 | EMA-Pullback | Uptrend, Low tagt EMA10/20, Close reclaimt EMA20 |
| S5 | Washout Long | 3 rote Tage ≤ −2×ATR%, Tag 3 schliesst oberes Drittel |

Regime-Filter auf NQ (QQQ-Proxy): RISK_ON / EXTENDED (keine neuen Entries) /
DEFENSIVE (nur S1+S5, halbe Grösse). Management: TP1 = 1/3 am technischen Nahziel →
BE-Stop; 1/3-Trim bei 7×ATR über SMA50; Runner mit EMA20/10-Trail; Hard-Exit unter SMA50.

## Ergebnisse

### Indizes (Kern-Universum)

| Zeitraum | n | WR | PF | Sum R | Max DD | CAGR |
|---|---|---|---|---|---|---|
| Gesamt | 582 | 39.2 % | **1.01** | +2.7 | 20.4 % | −0.0 % |
| IS 2013–2020 | 334 | 37.4 % | 0.99 | −2.8 | 20.4 % | −0.3 % |
| OOS 2021–2026 | 248 | 41.5 % | 1.04 | +5.6 | 12.5 % | +0.4 % |

**Break-even. Kein Edge.** Nach Kosten bleibt auf Indizes nichts übrig.

### Commodities (Robustheits-Gruppe)

| Zeitraum | n | WR | PF | Sum R | Max DD | CAGR |
|---|---|---|---|---|---|---|
| Gesamt | 447 | 39.8 % | **1.34** | +81.9 | 12.6 % | +3.1 % |
| IS 2013–2020 | 231 | 39.4 % | **1.03** | +3.6 | 12.6 % | +0.1 % |
| OOS 2021–2026 | 216 | 40.3 % | **1.71** | +78.4 | 12.1 % | +7.6 % |

**Gesamter Gewinn stammt aus 2021–2026 (Commodity-Bull-Regime).** In den 8 Jahren
davor: flat. Das ist Regime-Abhängigkeit, kein bewiesener struktureller Edge.

### Kandidaten im Detail

**S2 Cup-and-Handle (Indizes):** Gesamt PF 1.57 (n=60) sieht gut aus — aber
IS PF 0.48 vs OOS PF 3.14. Wer das 2013–2020 gehandelt hätte, hätte 8 Jahre
verloren und vor dem profitablen Regime aufgegeben. **Nicht robust, n zu klein.**

**S3 EMA-Pullback (Commodities):** PF 1.35 (n=401), 5 von 6 Instrumenten positiv
(nur NG negativ) — die beste Cross-Sectional-Konsistenz im Test. Aber zeitlich
instabil: IS 1.04, OOS 1.71. **Interessantester Kandidat, aber Regime-getrieben.**

**S1 und S5:** Zu wenige Trades (n=27 bzw. n=21 über alle Märkte) für eine Aussage.

### Exit-Analyse (Indizes)

| Exit | n | Sum R |
|---|---|---|
| EMA-Trail (Runner) | 127 | **+290.3** |
| Stop nach TP1 (BE) | 80 | +34.4 |
| SMA50-Break | 57 | −4.5 |
| Stop Loss | 318 | −317.5 |

Die Runner-Exits tragen den gesamten Gewinn; die Stop-Quote (55 %) frisst ihn auf.
Klassisches Momentum-Profil: der Edge — falls vorhanden — sitzt im **Exit/Trailing**,
nicht im Entry.

## Fazit

1. **Kein handelbarer Edge auf Indizes** (PF 1.01 nach Kosten).
2. **Commodities-Version profitierte vom 2021+-Regime** — nicht als Edge belegbar.
3. Die eigentliche MP-1-These („kaufe die stärksten Einzelaktien im Momentum-Regime")
   ist mit diesen Daten **nicht testbar**. Index-Futures sind ein schwacher Proxy,
   weil das Alpha in der Einzeltitel-Selektion (Leadership, Sektor-Rotation) stecken
   soll, nicht im Index-Timing.
4. Vor einem Live-Einsatz: Einzelaktien-Daten beschaffen (Netzwerk-Policy lockern
   oder Norgate/Polygon), Survivorship-Bias sauber behandeln, dann S2/S3 auf
   Aktien-Universum testen.
