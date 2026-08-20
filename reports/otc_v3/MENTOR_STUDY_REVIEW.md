# Review der OTC-Mentor-Studien (Dollar-Paare, Indizes, Crosses)

Vier PDFs des Mentors (Online Trading Campus, Juli 2026): 8 Dollar-Paare
(10 J., 1'770 Trades, 77.6 % @1:1 / 48.8 % @1:2), 4 US-Indizes (bis 29 J.,
Buy-only, 79.4 % @1:1, Valuation-Filter → +0.98R @1:2), 21 Crosses (10 J.,
4'145 Trades, 78.0 % @1:1 / 48.9 % @1:2, 28/28 Jahre profitabel).
Protokoll: jede frische Zone, First Touch, Limit am Proximal, Stop 1/3
Zonenhöhe hinter Distal, Ziele 1:1 und 1:2 separat, keine Kosten.

## Replikation auf unseren Daten

`backtest/run_otc_replication.py`: v3-Port im Studien-Preset (V3-Basis­verhalten
ohne Bernds Erweiterungen, Preferred, Skip 0, Loss first, Stop 33.33 %),
Wochenend-Stubs entfernt (261 Bars/Jahr wie in der Studie), letzte 10 Jahre.
Instrumente: 6E/6B/6J/6S/6A/6C/6N (7 ihrer 8 Dollar-Paare) und exakt
dieselben 21 Crosses.

| Pool | Konvention | 1:1 WR | 1:1 ØR | 1:2 WR | 1:2 ØR |
|---|---|---|---|---|---|
| Crosses (Studie) | Mentor-Ledger | **78.0 %** | +0.56R | **48.9 %** | +0.47R |
| Crosses (Replikation, n≈2'570) | Mentor-Ledger | 64.2 % | +0.29R | 38.8 % | +0.17R |
| Crosses (Replikation) | ehrlich, kostenlos | 46.2 % | −0.08R | 32.5 % | −0.03R |
| Crosses (Replikation) | ehrlich, mit Kosten | 44.3 % | −0.14R | 30.8 % | −0.11R |
| Majors-Futures (Replikation) | Mentor-Ledger | 62.1 % | +0.24R | 35.0 % | +0.05R |
| Majors-Futures (Replikation) | ehrlich, mit Kosten | 38.5 % | −0.25R | 26.0 % | −0.24R |

„Ehrlich" = Auflösung erst ab dem Bar NACH dem Fill (Fill-Bar: nur SL
zählt), SL vor TP, 1 Position/Instrument.

## Der entscheidende Befund: Die Fill-Kerze entscheidet den Test

Zerlegung der Ledger-1:1-Ergebnisse (Crosses, 2'575 Fills):

- **44.4 %** aller Trades werden **innerhalb der Fill-Kerze** als Gewinner
  gewertet (Tageskerze berührt das Limit UND spannt das 1R-Ziel, SL unberührt)
- 12.2 % Fill-Kerze trifft SL und TP → Loss first (das deckt die Studie ab)
- nur **38.7 %** überleben die Fill-Kerze unentschieden — und diese
  gewinnen **51.1 %** (Breakeven-Anforderung: 50 %)

Verifikation mit 4H-Sub-Bars (tatsächliche Intraday-Reihenfolge statt
Annahme): Von den 1'144 „Same-bar-Gewinnern" der Daily-Auflösung sind
**34 % in Wahrheit Verlierer** (Tageshoch lag VOR der Limit-Berührung).
Gesamt-Winrate 1:1 auf 4H-Auflösung: **49.7 % (konservativ) bis 57.6 %
(optimistisch)** — statt 64.2 % (Daily-Ledger). Vor Kosten also um
Breakeven, nach Kosten flach bis negativ.

Dazu passend: Der Random-Entry-Benchmark der Studie (32.7 % @1:2) wird von
unseren ehrlich gefüllten Zonen-Trades fast exakt getroffen (32.5 %).
Der ausgewiesene „Edge über Zufall" (+14–17 Punkte) entsteht, weil
Random-Entries (Einstieg zum Bar-Kurs) das Same-Bar-Geschenk der
Limit-Fills nicht bekommen — der Vergleich misst die Konvention, nicht
den Markt.

## Was der Studie zugutezuhalten ist (und was repliziert)

Die relativen Befunde der Studien decken sich bemerkenswert mit unseren:

1. **BE bei 1R kostet** (−0.21 bis −0.27R/Trade bei ihnen; unser BE-Test:
   PF 1.05 → 0.71) — identischer Mechanismus, identische Arithmetik.
2. **Formationen (DBR/RBR/RBD/DBD) unterscheiden sich nicht belastbar** —
   deckt sich mit unserem Formation-Breakdown.
3. **„Beste Paare" auswählen funktioniert nicht** (Korrelation 0.0) —
   deckt sich mit unserem Detektor-/Instrument-Befund.
4. **Valuation-Edge ist regimeabhängig** (2011–2015 fast weg) — ehrlich
   ausgewiesen; deckt sich mit unseren IS/OOS-Sprüngen.
5. Kosten fehlen — wird offen gesagt („no spread, no commission").

Die Studien sind also methodisch überdurchschnittlich sauber für
Mentor-Material (Random-Benchmark, Lookahead-Check, Settings-Lock,
Era-Splits). Der eine strukturelle Fehler — Same-Bar-Auflösung von
Limit-Fills auf Tageskerzen — sitzt aber genau unter der Headline-Zahl
und trägt sie fast vollständig.

## Einschränkungen dieser Replikation

- Unser v3-Port ist Bernds Rekonstruktion des Mentor-Panels, nicht der
  Original-Indikator: Er findet ~130 Zonen/Paar/Dekade, die Studie ~360
  (EUR/USD). Die Zonen-Mengen sind also nicht identisch; die
  Konventions-Zerlegung ist davon unabhängig gültig (sie betrifft jeden
  Limit-Fill-Backtest auf Tageskerzen).
- Die noch höhere Studien-Winrate (78 % vs. unsere 64 % im selben
  Ledger) deutet auf engere/mehr Zonen hin — engere Zonen erhöhen den
  Same-Bar-Anteil weiter.
- DXY fehlt uns; 7 von 8 Dollar-Paaren abgedeckt.

## Fazit

Die Studien zeigen real existierende, replizierbare RELATIVE Effekte
(Management-Rangfolge, Formation-Flachheit, Regimeabhängigkeit), aber die
absolute Profitabilitäts-Aussage (77–79 % @1:1, +0.5R/Trade) beruht auf
der Daily-Same-Bar-Konvention. Auf 4H-verifizierter Reihenfolge und nach
Kosten kollabiert der Basis-Edge auf ≈ Breakeven — konsistent mit allen
unseren bisherigen ehrlichen Tests derselben Strategie-Familie.
