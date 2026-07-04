# Trading-Playbooks v2.1 — evidenzbasiert überarbeitet

Stand: 2026-07-02. **v2.1-Ergänzung** (nach Test des User-Setups,
reports/user_breakout/): B1 High-Breakout mit Sektor-Top-5 als zweites
Primär-Setup neben Cup-and-Handle; Sektor-Gate als Pflichtregel; B2
MA-Touch-Reclaim nur am 200er mit Sektorfilter und halber Grösse; B2 am
50er nicht handeln. Buy-Stop-Entries bestätigt. Details in §3b/§1.5. Jede Regel trägt einen Evidenz-Tag:
`[BT:x]` = eigener Backtest in diesem Repo, `[P:x]` = SSRN-Paper (siehe
reports/research/README.md), `[!]` = Schutzregel ohne direkten Test, aus
Verlust-Logik abgeleitet.

Evidenz-Hierarchie dieser Session:
- Stocks-Breakout (S2 × Momentum-Leaders): **positiver Edge belegt** (PF 1.47–1.91
  über alle 13 Grid-Zellen) — handelbar mit Auflagen.
- S/D auf FX/Indices/Metalle: **kein Edge nach ehrlichen Fills** (alle Ordertypen,
  alle Management-Varianten, alle 9 Sensitivitätszellen negativ) — nicht handelbar.

---

# PLAYBOOK 1 — Stock Momentum Breakout (PRIMÄR)

## 1. Universum & Selektion

- **R1.1** Handelbar sind nur US-Aktien mit Ø-Dollar-Volumen ≥ $20 M/Tag und
  Preis ≥ $10. `[!]` (Liquiditäts-/PEAD-Kostenbefund `[P:Chordia]`)
- **R1.2** Monatliches Momentum-Ranking am Monatsultimo: 126-Tage-Return ohne
  die letzten 5 Tage. Nur **Quintil 1 und 2** (Top 40 %) sind handelbar; das
  Ranking gilt für den Folgemonat. `[BT:stock_selection — monotoner Gradient
  Q1>Q3>Q5, S2 auf Leaders PF 2.01 vs Laggards 1.10]`
- **R1.3** Zusätzlicher Vorrang: Titel innerhalb 15 % ihres 52-Wochen-Hochs.
  `[P:52W-High — Nähe zum 52W-Hoch trägt den Momentum-Effekt]`
- **R1.4** Max. 3 offene Positionen aus demselben Sektor-Cluster. `[!]`
- **R1.5 Sektor-Gate (v2.1):** Handelbar nur Titel, deren GICS-Sektor im
  Top-5-Rang (von 11) liegt. Sektor-Rang = Blend der equal-weight
  21/63/126-Tage-Returns, Vortagesstand. Grösster gemessener Einzel-Hebel:
  +0.22 R/Trade auf High-Breakouts (PF 1.94 → 2.46). `[BT:user_breakout]`

## 2. Regime-Filter (täglich, vor jeder neuen Order)

Referenz: QQQ (oder NQ-Futures), Daily.

- **R2.1 RISK_ON** = Close > SMA50 UND Close > EMA20 UND Distanz zur SMA50
  < 7×ATR50 → neue Entries erlaubt, volle Grösse. `[BT:mp1]`
- **R2.2 EXTENDED** = Distanz ≥ 7×ATR50 ODER 12-Tage-Return > +10 % → keine
  neuen Entries; bestehende Positionen laufen nach Plan weiter. `[BT:mp1]`
- **R2.3 DEFENSIVE** = Close < SMA50 → keine neuen Breakout-Entries. `[BT:mp1]`
- **R2.4 Crash-Rebound-Sperre:** Nach einem Tagestief ≥ 15 % unter dem
  50-Tage-Hoch gilt für 10 Handelstage nach dem Reversal-Tag Entry-Verbot,
  auch wenn R2.1 wieder erfüllt ist. Momentum-Selektion versagt genau in
  Rebound-Phasen. `[P:Daniel/Moskowitz — Momentum Crashes]`

## 3. Setup-Definition (objektiv, keine Interpretation)

Cup-and-Handle-Breakout:

- **R3.1 Basis:** 25–60 Handelstage, Tiefe 4–20 % vom Basis-Hoch. `[BT:breakout_opt]`
- **R3.2 Handle:** 3–8 Tage, vollständig im oberen Drittel der Basis,
  Ø-Tagesrange < 0.7×ATR20 (Kontraktion). `[BT:breakout_opt]`
- **R3.3 Trigger:** Daily-Close über Handle-Hoch UND Volumen ≥ 1.5× 20-Tage-Ø.
  Kein Intraday-Antizipieren des Closes. `[BT:stock_selection]`
- **R3.4 Kein Chasing:** Liegt der Trigger-Close > 2 % über dem Handle-Hoch,
  ist der Trade verpasst. Kein Nachspringen am Folgetag. `[!]`

## 3b. Zusatz-Setups (v2.1, getestet in reports/user_breakout/)

- **R3b.1 B1 High-Breakout (Primär, gleichrangig mit Cup-and-Handle):**
  Buy-Stop über 20-Tage-Hoch + 0.05×ATR14. SL = 10-Bar-Low − 0.5×ATR.
  TP 3R. Sektor-Gate (R1.5) Pflicht. `[BT:user_breakout PF 2.46, n=1559;
  Chop-Jahre 2015/2018 negativ → Regime-Filter R2 bleibt Pflicht]`
- **R3b.2 Extension-Filter:** Kein B1-Entry, wenn Trigger-Level ≥ 4×ATR über
  SMA50. Im Sample ohne messbaren Effekt (PF 2.46 vs 2.41) — bleibt als
  billige Versicherung für Extremregimes. Keine Edge-Erwartung.
  `[BT:user_breakout]`
- **R3b.3 B2 MA-Touch-Reclaim (Sekundär, HALBE Grösse):** Nur an der SMA200,
  nur mit Sektor-Gate. Touch-Bar mit Indecision-Kerze (Body ≤ 40 % der
  Range), Buy-Stop über Kerzen-High + 0.05×ATR, 5 Bars gültig, Cancel bei
  Bruch des Kerzen-Lows vor Trigger. SL = Kerzen-Low exakt (Puffer brachte
  hier nichts). TP 3R. `[BT:user_breakout PF 1.43, n=921]`
- **R3b.4 KEIN MA-Touch-Trade an der SMA50.** PF 1.1–1.2 ist nach
  Live-Slippage Rauschen. `[BT:user_breakout]`
- **R3b.5 Alle Stock-Entries per Buy-Stop, nie per Limit.** Konsistent mit
  der Order-Typ-Studie (Stop-Entries filtern fallende Messer).
  `[BT:entry_models]`

## 4. Entry

- **R4.1** Market-Order in den letzten 15 Minuten des Trigger-Tages (MOC-nah)
  oder zur Eröffnung des Folgetages. `[BT — Engine testet Close-Entry]`
- **R4.2 Earnings-Blackout:** Keine neue Position, wenn Earnings innerhalb der
  nächsten 5 Handelstage anstehen. `[!]`
- **R4.3 PEAD-Ausnahme:** Breakouts 1–3 Tage NACH einem positiven
  Earnings-Gap (Gap ≥ +3 % mit Volumen ≥ 1.5×Ø) sind bevorzugte Setups —
  Drift wirkt in Trade-Richtung. `[P:PEAD-Literatur; nicht separat
  rückgetestet — als Priorisierung, nicht als eigenes Setup]`

## 5. Stop-Loss (fix bei Entry, danach unantastbar)

- **R5.1** SL = Handle-Low − 0.5×ATR14. Struktur schlägt Entry-Abstand: die
  Struktur-Zeile dominiert im Grid jede ATR-vom-Entry-Variante in jeder
  TP-Spalte. `[BT:breakout_opt — Avg R +0.46 vs +0.19 bei E−1.0A, 3R]`
- **R5.2** Der halbe ATR-Puffer ist Pflicht — ohne ihn kosten Stop-Runs unter
  das Handle-Low messbar Performance (PF 1.45 statt 1.75). `[BT:breakout_opt]`
- **R5.3** Ist die SL-Distanz > 12 % vom Entry-Preis, Setup verwerfen
  (Positionsgrösse würde zu klein / Basis zu locker). `[!]`
- **R5.4** Kein Stop-Nachziehen, kein Erweitern, kein „mentaler Stop".
  Stops wirken bei Momentum-Strategien wertsteigernd — aber nur, wenn sie
  mechanisch bleiben. `[P:Kaminski/Lo; P:Han/Zhou/Zhu]`

## 6. Take-Profit

- **R6.1 Standard:** TP fix bei Entry + 3R, set-and-forget. `[BT:breakout_opt
  PF 1.75; BT:trade_mgmt — fix 3R gewinnt Expectancy in beiden Welten]`
- **R6.2 Aggressiv (optional, halbes Buch):** TP bei 4R — im Grid besser
  (PF 1.91), aber Randzelle; nur wenn 35 % Win-Rate psychologisch tragbar.
  `[BT:breakout_opt]`
- **R6.3 Keine Teilgewinne bei +1R.** Partials kaufen Win-Rate (58 %) und
  kleineren DD (15 %) für fast die Hälfte der Expectancy (0.25 vs 0.46 Avg R).
  Einzige zulässige Ausnahme: hartes Prop-Firm-DD-Limit. `[BT:breakout_opt;
  BT:trade_mgmt — M3 in beiden Welten schwächste Expectancy]`
- **R6.4** Zwischen Entry und TP/SL wird nichts angefasst. Kein Verschieben,
  kein „Sichern", kein vorzeitiger Exit wegen Chart-Gefühl. Overtrading ist
  der statistisch grösste Renditekiller für Privattrader. `[P:Barber/Odean]`

## 7. Positionsgrösse (VIX-gesteuert)

- **R7.1** Risiko pro Trade = 0.5 % × (17 ÷ VIX-Schlusskurs des Vortags),
  **Cap 0.75 %**, Floor 0.25 %. `[BT:breakout_opt]`
- **R7.2** Der Cap bei 0.75 % (nicht 1 %) ist bewusst: Der rohe Formel-Gewinn
  im Backtest war grösstenteils versteckter Hebel (Ø 0.68 % statt 0.5 %
  Risiko in der Low-VIX-Ära). Leverage-normalisiert liefert VIX-Sizing
  ~2 pp weniger Drawdown bei gleichem Ertrag — das ist der echte Effekt, den
  R7.1 einfangen soll. `[BT:breakout_opt normiert; P:Moreira/Muir;
  Kritik P:Cederburg]`
- **R7.3** Max. 6 offene Positionen; offenes Gesamtrisiko ≤ 3 %. `[!]`
- **R7.4** Neue Entries nur, wenn das realisierte Konto-Ergebnis der letzten
  5 Handelstage ≥ −2 % ist (Progressive-Exposure-Bremse). `[!]`

## 8. Zeitbudget (Vollzeitjob-tauglich)

- **R8.1** Screening 1× täglich nach US-Close ODER vor US-Open: Ranking-Check,
  Setup-Scan, Orders für den nächsten Tag. 20–30 Min. `[!]`
- **R8.2** Alle Orders als Bracket (Entry + SL + TP) — kein Intraday-Monitoring
  nötig. `[!]`

## 9. Journal & Kill-Kriterien

- **R9.1** Pro Trade festhalten: Datum, Ticker, Quintil, Regime, SL-Distanz,
  VIX, Ergebnis in R, Regel-Verstösse. `[!]`
- **R9.2 Kill-Kriterium Strategie:** Rollierende 40-Trade-Expectancy < 0 R
  ODER Konto-DD > 20 % → Livebetrieb stoppen, zurück ins Demo, Ursachenanalyse.
  `[!]`
- **R9.3 Regeländerungs-Sperre:** Regeländerungen nur nach ≥ 40 neuen Trades
  UND ausserhalb offener Positionen. Nie nach einem einzelnen Verlust. `[!]`

---

# PLAYBOOK 2 — S/D auf Forex/Indices/Metalle: NICHT LIVE HANDELN

**Status: Kein Edge belegt.** First-Touch-S/D mit Trendfilter ist auf 13 Jahren,
40 Instrumenten, 4 Ordertypen, 6 Management-Varianten und 9 Sensitivitätszellen
durchgehend negativ (bestes Modell −0.046 R/Signal). `[BT:entry_models]`

Falls du S/D trotzdem diskretionär handelst, minimieren diese Regeln den
Schaden — sie machen die Strategie nicht profitabel:

- **S1** Entry NIE per Limit am Zonenrand. Immer Stop-Order über dem
  Reaktions-High (Long) bzw. unter dem Reaktions-Low (Short). Das ist
  +0.12 bis +0.21 R/Signal besser als Limit — der grösste einzelne Hebel,
  den wir gemessen haben. `[BT:entry_models, CI schliesst 0 aus]`
- **S2** Management set-and-forget mit fixem 2–3R-Ziel. Chandelier/Trailing
  verlor seinen scheinbaren Vorsprung nach ehrlicher Same-Bar-BE-Abrechnung.
  `[BT:entry_models Revision der Management-Studie]`
- **S3** Verfallene Order = verpasster Trade. Wer der Bewegung nachjagt,
  handelt das Limit-Profil mit schlechterem Preis. `[BT:entry_models]`

**Redesign-Pfad (Forschung, kein Livebetrieb):** Zonen über Orderflow-Logik
statt Geometrie — runde Levels, frische Extremes, Session-Liquiditätsfenster
(London/NY), HTF-Konfluenz. Akademische Basis: S/R-Levels wirken über
Order-Cluster. `[P:Osler ×2]` Messlatte für jede neue Variante: deutlich
> 0 R/Signal auf dem paired Test-Setup aus `backtest/run_entry_verify.py`.

---

# GLOBALE KONTO-REGELN (beide Playbooks)

- **G1** Wochen-Stop: Realisierter Verlust ≥ 3 % in einer Woche → alle offenen
  Orders löschen, Rest der Woche flat. Positionen mit Bracket laufen aus. `[!]`
- **G2** Ein Instrument, eine Position. Keine Adds vor TP1/SL. `[!]`
- **G3** Backtest-Kennzahlen, gegen die live gemessen wird (Stocks-Playbook):
  Win-Rate ~38 %, Avg R ~+0.46, längste Verluststrecke im MC-Band bis ~15.
  Weicht Live nach 40 Trades massiv ab (Expectancy < 0), greift R9.2. `[BT]`
- **G4** Jede Regel dieses Dokuments ist mechanisch. Wenn eine Situation nicht
  von einer Regel abgedeckt ist, ist die Antwort: kein Trade. `[!]`

---

## Was sich gegenüber v1 geändert hat (und warum)

| Änderung | Alt | Neu | Evidenz |
|---|---|---|---|
| Stop-Platzierung | teils ATR vom Entry | nur Struktur (Handle-Low − 0.5×ATR) | Grid: Struktur dominiert jede Spalte |
| Take-Profit | Partials/Trailing-Mix | fix 3R set-and-forget | Partials kosten ~50 % Expectancy |
| Sizing | fix | VIX-invers mit Cap 0.75 % | echter Effekt = DD-Senkung, nicht Ertrag |
| S/D-Entries | Limit an Zone | Stop-Order nach Reaktion — aber Strategie gesamt nicht live | paired Test, CI > 0 |
| Trade-Management | aktiv | nichts anfassen zwischen Entry und Exit | Barber/Odean + eigene Replays |
| Regime | nur SMA-Filter | + Crash-Rebound-Sperre (R2.4) | Daniel/Moskowitz |
| Selektion | implizit | hartes Q1/Q2-Gate + 52W-High-Vorrang | Quintil-Gradient, 52W-Literatur |
