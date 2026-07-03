# SSRN-Research-Leseliste für die Breakout-/Swing-Strategie

Kuratiert am 2026-07-02. Auswahlkriterium: direkte Relevanz zu den in diesem
Repo getesteten Strategien (Momentum-Breakouts auf Aktien, VIX-Sizing,
Stop-Loss-Design, S/D-Zonen auf FX) — inklusive der Gegen-Papers.

## Direkt umsetzbar (höchste Relevanz)

1. **Moreira & Muir — Volatility-Managed Portfolios**
   https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2659431
   Weniger Risiko bei hoher Vol erhöht Sharpe-Ratios über Markt-, Momentum-,
   Value-Faktoren. Die akademische Basis für unser VIX-Sizing (Z2). Kontra
   lesen: Cederburg et al. (https://www.ssrn.com/abstract=3357038) — vieles
   überlebt Out-of-Sample und Kosten nicht.
2. **Han, Zhou, Zhu — Taming Momentum Crashes: A Simple Stop-Loss Strategy**
   https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2407199
   10 %-Stop reduziert Max-Monatsverlust von −50 % auf −11 %, Sharpe verdoppelt.
   Stützt unser Ergebnis: Stops + Momentum passen zusammen.
3. **Kaminski & Lo — When Do Stop-Loss Rules Stop Losses?**
   https://papers.ssrn.com/sol3/papers.cfm?abstract_id=968338
   Bei Random Walk zerstören Stops Erwartungswert; bei Momentum-Regimes
   addieren sie Wert. Erklärt, warum Stops bei deinen Breakouts funktionieren,
   bei Mean-Reversion aber schaden würden.
4. **George & Hwang-Linie: 52-Week-High-Momentum international**
   https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1364566
   Nähe zum 52W-Hoch erklärt Momentum-Profite; profitabel in 18/20 Märkten,
   signifikant in 10 — aber nach Kosten oft weg. Direkt relevant für
   Cup-and-Handle nahe ATH.
5. **Daniel & Moskowitz — Momentum Crashes**
   https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2371227
   Momentum stürzt in Markt-Rebounds nach Panik ab. Begründet den
   Regime-Filter: keine frischen Momentum-Longs direkt nach Crash-Tiefs.

## Fundament (Trend/Momentum-Klasse)

6. **Moskowitz, Ooi, Pedersen — Time Series Momentum**
   https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2089463
   1–12-Monats-Persistenz über 58 Futures-Märkte. Kontext für die
   Trend-Komponente; Kritik: Teil des Effekts ist Volatility-Scaling
   (https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2786955).
7. **Zhou & Zhu — A Theory of Technical Trading Using Moving Averages**
   https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326650
   Warum MA-Regeln theoretisch Wert tragen können — Basis für 50-SMA-Filter.
8. **Lo, Mamaysky, Wang — Foundations of Technical Analysis**
   https://papers.ssrn.com/sol3/papers.cfm?abstract_id=228099
   Der Klassiker: Chart-Muster (inkl. Cup-ähnliche) statistisch erkennbar und
   informativ — aber Informationsgehalt ≠ automatisch profitabel.

## Warnungen (Pflichtlektüre vor Live-Gang)

9. **Barber & Odean — Trading is Hazardous to Your Wealth**
   https://papers.ssrn.com/sol3/papers.cfm?abstract_id=219228
   Vieltrader verdienen 11.4 % p.a. vs 17.9 % Markt. Overtrading ist der
   grösste Feind — passt zu unserem Befund, dass Set-and-forget gewinnt.
10. **Barber, Lee, Liu, Odean — The Cross-Section of Speculator Skill**
    https://papers.ssrn.com/sol3/papers.cfm?abstract_id=529063
    Nur ~1 % der Daytrader schlagen nach Kosten dauerhaft den Markt.
11. **Kuang, Schröder, Wang — Illusory Profitability of Technical Analysis**
    https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1586278
    30 % p.a. Backtest-Renditen verschwinden nach Data-Snooping-Korrektur —
    exakt das Muster, das wir in der S/D-Studie live erlebt haben.
12. **Park & Irwin — The Profitability of Technical Analysis: A Review**
    https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID603481_code17745.pdf?abstractid=603481
    Meta-Studie: TA-Profite konzentrieren sich vor ~1990, danach erodiert.

## Speziell für FX / S/D-Zonen

13. **Osler — Support for Resistance: Technical Analysis and Intraday Exchange Rates**
    https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID888805_code387943.pdf?abstractid=888805&mirid=1
    S/R-Levels unterbrechen Intraday-Trends messbar — aber Prognosekraft
    variiert stark. Der beste akademische Beleg, dass Zonen *etwas* messen.
14. **Osler — Currency Orders and Exchange-Rate Dynamics**
    https://papers.ssrn.com/sol3/papers.cfm?abstract_id=923370
    Cluster von Stop- und Limit-Orders erklären, warum S/R funktioniert wenn
    es funktioniert: Orderflow, nicht Magie. Relevanz: Zonen-Definitionen,
    die Orderflow-Logik abbilden (runde Levels, frische Extremes), sind
    plausibler als geometrische Basen.

## Für Earnings-Phasen (Breakout-Katalysatoren)

15. **Zhou & Zhu — Jump on the Post-Earnings Announcement Drift**
    https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2066854
    15.3 % p.a., Sharpe 1.52 für Jump-basierte PEAD-Strategie. Achtung:
    Chordia et al. (https://papers.ssrn.com/sol3/papers.cfm?abstract_id=972758)
    zeigen, dass Kosten 63–100 % der Papierprofite fressen und der Effekt in
    illiquiden Titeln sitzt. Für dich relevant: Breakouts NACH Earnings mit
    Gap+Volumen sind statistisch begünstigt (Drift-Richtung), Earnings-
    Blackout vor dem Event bleibt richtig.

## Querbezüge zu unseren Backtest-Befunden

| Unser Befund | Bestätigt durch |
|---|---|
| Struktur-Stop + weites TP bei Breakouts | Kaminski/Lo (Momentum-Regime), Han/Zhou/Zhu |
| VIX-Sizing = weniger DD, kaum mehr Ertrag | Moreira/Muir vs Cederburg-Kritik |
| S/D-First-Touch ohne Edge nach ehrlichen Fills | Kuang et al. (Data-Snooping), Park/Irwin |
| Set-and-forget schlägt aktives Management | Barber/Odean (Overtrading) |
| Selektion (Leaders) > Entry-Timing | 52W-High-Literatur |
