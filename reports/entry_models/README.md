# Order-Typ-Studie: Limit vs Stop vs Close-Confirm an S/D-Zonen

**Frage:** Ändert sich das (negative) S/D-Ergebnis, wenn man statt Limit-Orders
Stop-Orders (Entry erst bei Rückkehr des Preises) verwendet?

## Design

Vier Entry-Modelle auf **identischen** First-Touch-Signalen (11'426 Signale,
40 Instrumente: 28 Forex, 6 Indizes, 4 Metalle; 4H, 2013–2026):

| Modell | Mechanik |
|---|---|
| LIMIT | Resting Limit am proximalen Zonenrand, füllt beim Touch |
| STOP_HIGH | Stop-Order über dem High des Touch-Bars + 0.1×ATR, gültig 6 Bars |
| STOP_RECLAIM | Stop am Zonenrand + 0.1×ATR (Preis muss aus der Zone zurückkommen) |
| CLOSE_CONFIRM | Market am Close des ersten 4H-Bars, der über dem Rand schliesst |

Konservative Regeln überall: Stop-vor-Target, Trigger-Bar-mit-SL-Berührung = −1R,
Violation-vor-Trigger = Order storniert.

## Adversarial Audit (3 unabhängige Agents) und Korrekturen

Ein Code-Audit vor der Ergebnis-Interpretation fand vier substanzielle Punkte —
**alle in Richtung „Resultate zu optimistisch"** — die für den finalen Lauf
korrigiert wurden:

1. **BE-Stop-Reprieve:** Ein im Bar nachgezogener Break-Even-Stop wurde nie gegen
   das Tief desselben Bars geprüft (betraf 32.8 % der +1R-Bars; bis +0.055R/Trade
   zu gut für Partial-/Trail-Varianten). → Konservative Same-Bar-Prüfung ergänzt.
2. **Kommission wurde in dieser Pipeline nie belastet** (~0.02R/Trade). → Belastet.
3. **SL nutzte die ATR des noch laufenden Touch-Bars** (pro-Strategie-Leak). →
   ATR des letzten abgeschlossenen Bars.
4. **Position-Blocking machte die Signal-Sets zwischen Modellen unvergleichbar** →
   Primärlauf ohne Blocking: jedes Signal unter jedem Modell (paired design),
   Metrik = R pro Signal (ungefüllt = 0), Wochen-Block-Bootstrap-CI.

## Ergebnis (korrigierter Paired-Lauf)

**R pro Signal (ungefüllt = 0R), Management M2 fix 3R:**

| Modell | R/Signal | Fill-Rate | PF/Fill | Diff vs LIMIT [95% CI] |
|---|---|---|---|---|
| LIMIT | −0.170 | 100 % | 0.79 | — |
| **STOP_HIGH** | **−0.046** | 38 % | 0.85 | **+0.124 [+0.086, +0.161]** |
| STOP_RECLAIM | −0.141 | 78 % | 0.78 | +0.029 [+0.003, +0.054] |
| CLOSE_CONFIRM | −0.095 | 64 % | 0.81 | +0.075 [+0.048, +0.101] |

M4 (Chandelier) zeigt dieselbe Rangfolge mit grösseren Differenzen
(STOP_HIGH +0.211 [+0.178, +0.246] vs LIMIT).

Sensitivitäts-Grid STOP_RECLAIM (Buffer 0/0.1/0.25 ATR × Gültigkeit 3/6/12 Bars):
**alle 9 Zellen negativ** (PF 0.80–0.84).

## Antworten

1. **Ja, Stop-Orders sind an S/D-Zonen messbar besser als Limit-Orders.** Der
   paired Unterschied ist statistisch belastbar (CIs schliessen 0 aus). Rangfolge:
   STOP_HIGH > CLOSE_CONFIRM > STOP_RECLAIM > LIMIT. Mechanik: Die Stop-Order
   überspringt 62 % der Signale — überproportional die fallenden Messer, die der
   Limit-Trader als −1R einsammelt.
2. **Aber: Kein Order-Typ macht die Strategie profitabel.** Bestes Modell
   (STOP_HIGH) verliert immer noch ~0.05R pro Signal. Der Order-Typ verändert,
   *wie* man verliert — nicht *ob*. Das Problem ist das Zonen-/Signalkonzept
   selbst (First Touch + Trendfilter), nicht die Ausführung.
3. **Revision der Management-Studie:** Mit der ehrlichen Same-Bar-BE-Regel
   verliert der Chandelier-Trail (M4) seinen scheinbaren Vorsprung in der
   S/D-Welt (PF/Fill 0.53–0.57 vs M2 0.78–0.79). Der frühere „M4 gewinnt"-Befund
   war teilweise ein Artefakt des BE-Reprieve-Bugs. **Set-and-forget (M2) ist
   unter ehrlicher Abrechnung die robustere Wahl** — konsistent mit der
   Stocks-Welt.

## Einschränkungen

- Stop-Fills am Trigger + identische Friction: real bekommen Stop-Markets bei
  Gaps schlechtere Fills (~2–3 % der 4H-FX-Bars, mehr bei Indizes) — die
  Stop-Überlegenheit ist also eher etwas ÜBERschätzt; am Vorzeichen ändert das
  nichts.
- ~90 implizite Vergleiche über die Studien: einzelne positive Zellen (z. B.
  Indizes PF 1.03) sind unter der Null-Hypothese zu erwarten und werden nicht
  interpretiert.
- Swap-Kosten weiterhin nicht belastet (~0.01–0.02R bei Ø 2 Nächten Haltezeit) —
  würde alles weiter verschlechtern.
