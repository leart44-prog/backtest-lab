# Studien zum Trade-Management — kuratiert & erklärt

Ergänzung zur Haupt-Leseliste (README.md). Fokus: Was sagt die Forschung zu
Stops, Trailing, Take-Profit, Teilgewinnen und Sizing — und wo deckt sie sich
mit unseren eigenen Backtests?

## 1. Statische Stop-Losses

**Kaminski & Lo — When Do Stop-Loss Rules Stop Losses? (2007)**
https://papers.ssrn.com/sol3/papers.cfm?abstract_id=968338
Kernaussage: Der Wert eines Stops hängt vom Preisprozess ab. Bei Random Walk
senken Stops den Erwartungswert (man realisiert Verluste, die sich sonst
ausmitteln). Bei positiver Autokorrelation (Momentum) addieren Stops Wert,
weil Verlierer weiterfallen. Praktisch: Stops gehören zu Momentum-/Breakout-
Strategien; in Mean-Reversion-Systemen sind sie strukturell schädlich.

**Lo & Remorov — Stop-Loss Strategies with Serial Correlation, Regime
Switching, and Transaction Costs (2015)**
https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID2695383_code1698370.pdf?abstractid=2695383&mirid=1
Formalisiert das mit Regime-Switching: Stops wirken am besten, wenn Verluste
Regime-Information tragen (Bärenregime erkannt = raus). Praktisch: der
SMA50-Hard-Exit im Playbook ist genau so ein Regime-Stop.

**Lei & Li — The Value of Stop Loss Strategies (2009)**
https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1214737
Ernüchterung als Kontrast: Auf Buy-and-Hold-Aktienportfolios verbessern Stops
die Rendite NICHT — ihr Wert ist fast reine Risikoreduktion. Praktisch: Wer
Stops als Renditequelle verkauft, übertreibt; sie sind ein Verteilungsformer.

**Han, Zhou, Zhu — Taming Momentum Crashes (2014)**
https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2407199
Auf Momentum-Portfolios: 10 %-Stop senkt Max-Monatsverlust von −50 % auf
−11 %, Sharpe verdoppelt. Die stärkste Pro-Stop-Evidenz — und sie gilt exakt
für den Strategietyp des Playbooks.

## 2. Trailing Stops

**Dai, Marshall, Nguyen, Visaltanachoti — Risk Reduction Using Trailing
Stop-Loss Rules (2019)**
https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3338243
Grosse Empirie: Trailing Stops haben NIEDRIGERE Durchschnittsrenditen als
Buy-and-Hold, aber bessere risikoadjustierte Kennzahlen und deutlich weniger
Left-Tail (besonders bei später delisteten Aktien). Praktisch: Trailing =
Versicherung, nicht Renditebooster — konsistent mit unserem Befund, dass der
Chandelier-Trail nach ehrlicher Abrechnung keinen Expectancy-Vorteil hat.

**Leung & Zhang — Optimal Trading with a Trailing Stop (2017)**
https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2895437
Theorie-Papier: leitet optimale Liquidationsregeln unter Trailing Stops her;
zeigt, dass die optimale Trail-Distanz von Drift/Vol-Verhältnis abhängt —
enge Trails nur bei starkem Drift. Praktisch: fixe „3×ATR für alles"-Regeln
sind eine Vereinfachung; bei schwachem Trend-Drift ist gar kein Trail besser.

## 3. Take-Profit-Platzierung

**Battle — A Simple Trading Strategy with a Stop-Loss and Take-Profit Order**
https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5859402
Analytik zur SL/TP-Geometrie: Es existieren Bedingungen (Drift, Autokorrelation),
unter denen ein Stop den Mittelwert ERHÖHT und die Varianz senkt; liefert
eine Kelly-artige Näherungsformel für das optimale Stop-Level. Praktisch:
SL/TP-Verhältnisse sind kein Geschmacksthema, sondern eine Funktion des
Signal-Drifts — bei starkem Drift (Breakouts auf Leaders) weite TPs, exakt
unser Grid-Befund (2R → 4R monoton besser).

**Arratia & Dorador — On the Effectiveness of Stop-Loss Rules (2018)**
https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID3087196_code2863061.pdf?abstractid=3087196&mirid=1
Modelliert Overnight-Gaps explizit (Bootstrap): Stops sind in Gap-Märkten
schlechter als ihr Backtest-Bild, weil Fills jenseits des Levels passieren.
Praktisch: bestätigt unser Audit-Finding F3 (Gap-through-Stop ~0.3R Schaden
in 2.7 % der Fälle; mehr bei Indizes).

## 4. Der Verhaltens-Gegner: Disposition-Effekt

**Odean — Are Investors Reluctant to Realize Their Losses? (1998)**
https://papers.ssrn.com/sol3/papers.cfm?abstract_id=94142
10'000 Brokerage-Konten: Anleger verkaufen Gewinner zu früh und halten
Verlierer zu lang — und die gehaltenen Verlierer underperformen die
verkauften Gewinner anschliessend. Praktisch: Teilgewinne bei +1R sind die
systematisierte Form dieses Fehlers. Unser Backtest bezifferte den Preis:
~50 % der Expectancy.

**Barber, Lee, Liu, Odean — Is the Aggregate Investor Reluctant to Realize
Losses? Evidence from Taiwan (2007)**
https://papers.ssrn.com/sol3/papers.cfm?abstract_id=945014
Der Effekt gilt marktweit (84 % aller Trader betroffen), ist also kein
Nischenphänomen. Praktisch: mechanische Bracket-Orders (TP+SL bei Entry,
danach nichts anfassen) sind die wirksamste Gegenmassnahme.

**Ben-David & Hirshleifer — Are Investors Really Reluctant to Realize Their
Losses? (2012)**
https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID3217315_code2024.pdf?abstractid=3217315&mirid=1
Differenzierung: Das Verkaufsmuster folgt eher Überzeugungs-Updates
(Spekulationsmotiv) als reiner Verlustaversion — V-förmige Verkaufsfunktion
um den Einstandspreis. Praktisch: auch „rationale" Gründe fürs frühe
Gewinnmitnehmen produzieren dasselbe schädliche Muster; die Regel schützt
vor beidem.

## 5. Exits in Trendfolge-Systemen

**Hachemian, Tavernier, Van Royen — The Significance of Trading Frequency
and Stop Loss in Trend Following Strategies (2013)**
https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID2349848_code1794015.pdf?abstractid=2349848&mirid=1
Auf MA-Crossover-Systemen über globale Futures: Stops verhindern zuverlässig
die schweren Verluste, verbessern aber die normalen Ergebnisse kaum;
zu häufiges Handeln (schnelle Signale) kostet mehr als es bringt.
Praktisch: deckt sich mit unserem MA-Längen-Befund (langsam schlägt schnell).

**Sepp — The Science and Practice of Trend-Following Systems (2018)**
https://papers.ssrn.com/sol3/Delivery.cfm/3167787.pdf?abstractid=3167787&mirid=1
Verbindet Autokorrelation und erwartbare Sharpe: Trendfolge lohnt, wo
langfristige Autokorrelation positiv ist; der Exit (Signalumkehr vs Stop vs
Ziel) ist sekundär gegenüber der Marktauswahl. Praktisch: erst Markt/Signal,
dann Management — die Reihenfolge, die unsere gesamte Session bestätigt hat.

## 6. Position-Sizing

**MacLean, Thorp, Ziemba — The Kelly Capital Growth Investment Criterion (2011)**
https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1797366
Das Standardwerk: Voll-Kelly maximiert langfristiges Wachstum, ist aber
psychologisch und bei Schätzfehlern untragbar; Fractional Kelly tauscht
Wachstum gegen drastisch weniger Drawdown. Praktisch: 0.5 %-Risiko pro Trade
ist de facto ein sehr konservatives Fractional Kelly — richtig so.

**Sinclair — Confidence Intervals for the Kelly Criterion (2014)**
https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2457368
Kelly-Inputs (Win-Rate, Payoff) sind Schätzungen mit breiten Fehlerbändern;
schon kleine Fehler kippen Voll-Kelly ins Ruinöse. Praktisch: mit n=397
Trades ist unsere Expectancy-Schätzung ±breit — noch ein Grund für den
0.75 %-Cap beim VIX-Sizing.

**Sukhov — Bayesian Kelly Criterion with Parameter Uncertainty (2026)**
https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6195358
Bayesianisches Kelly mit Unsicherheits-Schrumpfung: reduziert Max-DD um
40–60 % bei 85–95 % der Wachstumsrate. Praktisch: State of the Art, falls
du Sizing je dynamisch machen willst; die Richtung ist immer „kleiner als
die Punktschätzung suggeriert".

## 7. Meta-Befund: Teilgewinne/Scaling-Out sind akademisches Niemandsland

Eine gezielte Suche nach Studien zu Partial-Profit-Taking/Pyramiding liefert
fast nur Patente und Reinforcement-Learning-Paper — **es gibt keine solide
empirische Literatur, die Teilgewinnmitnahmen als renditeförderlich belegt.**
Die Praxis-Folklore („immer Teilgewinne sichern") steht damit ohne Evidenz
da, während Disposition-Effekt-Forschung und unsere eigenen Replays (beide
Welten: M3 schwächste Expectancy) dagegen sprechen. Teilgewinne sind ein
Psychologie-/Constraint-Werkzeug (Prop-Firm-Limits), kein Edge-Werkzeug.

## Zuordnung zu den Playbook-Regeln

| Playbook-Regel | Gestützt durch |
|---|---|
| R5.1–5.4 Struktur-Stop, mechanisch | Kaminski/Lo, Han/Zhou/Zhu, Lo/Remorov |
| R6.1 fix 3R statt Trailing | Dai et al. (Trailing = Versicherung), eigener Replay |
| R6.3 keine Partials | Odean, Ben-David/Hirshleifer, Meta-Befund §7, eigener Grid |
| R6.4 nichts anfassen | Barber/Odean, Bracket-Order-Logik |
| R7.1–7.2 0.5 % + Cap | MacLean/Thorp/Ziemba, Sinclair (Schätzfehler) |
| SMA50-Hard-Exit | Lo/Remorov (Regime-Stop) |
| Gap-Vorsicht bei Indizes | Arratia/Dorador |
