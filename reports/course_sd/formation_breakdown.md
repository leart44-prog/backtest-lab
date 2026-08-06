# Formations-Aufschlüsselung: RBR vs DBR vs RBD vs DBD

Auswertung der vorhandenen Trade-Logs (kein neuer Lauf; fcode wurde pro Trade
mitgeloggt). Ranking-Frage: Welche Zonen-Typen funktionieren am schlechtesten?

## C1 BASE — grösste Stichprobe (n=29'848)

| Formation | n | WR | PF | Avg R |
|---|---|---|---|---|
| DBR (Reversal Demand) | 6'539 | 26.7 % | **0.86** | **−0.110** |
| RBR (Continuation Demand) | 7'840 | 25.7 % | 0.81 | −0.145 |
| RBD (Reversal Supply) | 7'612 | 25.3 % | 0.80 | −0.156 |
| **DBD (Continuation Supply)** | 7'857 | 25.0 % | **0.78** | **−0.168** |

## Mit Valuation-Gate (C2 / C5) — das Ranking dreht sich zugunsten der Reversals

| Formation | C2 Avg R | C5 Avg R |
|---|---|---|
| **RBD (Reversal Supply)** | **−0.028** (PF 0.96) | **−0.006** (PF 0.99) |
| DBR (Reversal Demand) | −0.091 | −0.089 |
| DBD (Continuation Supply) | −0.139 | −0.046 |
| RBR (Continuation Demand) | −0.154 | **−0.265** (PF 0.67) |

Kombiniert:
- **Reversal-only (DBR+RBD) mit Valuation:** PF 0.92–0.94, Avg R −0.043 bis
  −0.057 — am nächsten an der Wasserlinie, aber immer noch negativ.
  Frequenz ~0.5 Trades/Woche.
- Continuation-only (RBR+DBD) mit Valuation: PF 0.80–0.81, Avg R ≈ −0.15.

## Formation × Asset-Klasse (C1)

Einzige positive Zellen im gesamten Grid:
- **DBR auf Indizes: +0.050 Avg R** (n=877)
- **DBR auf Metallen: +0.030 Avg R** (n=515)

Schlechteste Zellen:
- **DBD auf Indizes: −0.244** (Continuation-Shorts gegen den strukturellen
  Long-Bias von Aktienindizes)
- DBD auf Metallen: −0.217
- RBD auf Metallen: −0.200

## IS/OOS-Stabilität (C1)

| Formation | IS 2013–20 | OOS 2021–26 |
|---|---|---|
| RBR | −0.180 | −0.097 |
| DBR | −0.116 | −0.101 |
| RBD | −0.158 | −0.153 |
| DBD | −0.160 | **−0.180** |

DBD ist in beiden Perioden am schwächsten bzw. verschlechtert sich OOS.

## Befunde

1. **DBD (Drop-Base-Drop, Continuation Supply) ist der klarste Verlierer** —
   letzter oder vorletzter Platz in jeder Konfiguration, beiden Perioden und
   den meisten Asset-Klassen. Continuation-Shorts kämpfen strukturell gegen
   den Long-Drift von Indizes/Metallen im Sample.
2. **Reversal-Formationen (DBR, RBD) schlagen Continuation-Formationen
   (RBR, DBD) systematisch, sobald das Valuation-Gate aktiv ist** — kohärent:
   Mean-Reversion-Filter (over/undervalued) passt konzeptionell zu
   Umkehr-Zonen, nicht zu Fortsetzungs-Zonen. RBR + undervalued ist die
   schlechteste Kombination (PF 0.67 in C5): Continuation-Longs in fallende
   Märkte kaufen widerspricht sich selbst.
3. **Kein Formations-Subset ist profitabel.** Auch die beste Kombination
   (Reversal-only + Valuation, PF 0.92–0.94) bleibt unter Wasser — die
   Formations-Wahl verschiebt ~0.10–0.15 R/Trade, dreht aber das Vorzeichen
   nicht.
4. Für diskretionäres Traden nach diesem System heisst das: DBD streichen,
   RBR nie mit Undervalued-Signal kombinieren, Fokus auf DBR-Longs
   (insb. Indizes/Metalle) und RBD-Shorts an Overvalued-Extremen.
