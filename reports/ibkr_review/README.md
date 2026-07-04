# IBKR-Konto-Review — Trades Juni–Juli 2026

**Datenbasis:** IBKR-API (Live-Konto), Trades 2026-06-08 bis 2026-07-02
(ältere Historie via API nicht verfügbar — effektiv 4 Wochen, 14 Round-Trips).
Konto: CHF 12'720 NLV, aktuell flat. **Mit n=14 ist kein statistischer
Backtest möglich** — dies ist ein Performance-Audit + Playbook-Abgleich +
Trade-für-Trade-Counterfactual mit echten IBKR-Kursdaten.

## Performance-Rekonstruktion

- **Netto-P/L: +1'499 USD in 4 Wochen** (~+9–12 % aufs Konto) — starker Monat.
- **Konzentration: OSCR (+778) + AMD (+700) = 99 % des Gesamt-P/L.**
  Die übrigen 12 Round-Trips summieren auf +21 USD (~Kommissions-Rauschen).
- Win-Rate 86 % (12/14) — typisch für schnelles Gewinnmitnehmen + enge BE-Stops.
- Haltezeiten: Median < 1 Tag (1.2 h bis 24 d). Nur OSCR (24 d) war ein
  echter Swing-Trade — und wurde der grösste Gewinner.

## Playbook-Abgleich (v2.3)

| Regel | Befund |
|---|---|
| Buy-Stops statt Limits (R3b.5) | **5 von 10 Pending-Entries waren Limits** (NVDA, GOOGL, SNEX, HOOD ×2) — gegen die eigene Regel |
| Positionsgrösse / Risiko | **HOOD 21k USD = ~133 % des Kontos** (Margin), AMD 86 %, TSM 51 %. TSM-Verlust −245 USD ≈ 1.5–1.9 % Kontorisiko ≈ 3–4× Playbook (0.5 %) |
| Set-and-forget (R6.4) | Verletzt in 10/14 Trades: Markt-Exits nach +0.9–2 % am selben/nächsten Tag |
| Churn/Overtrading | ADI: Re-Buy **9 Sekunden** nach Exit; HOOD: Re-Entry **1 Minute** nach Stop-Out; PDT-Zähler ausgeschöpft (T+0/T+1 = 0) |
| Verlierer schneiden | ✅ Vorbildlich: TSM als einziger Verlust schnell realisiert, BE-Stops konsequent (NVDA, FRO, ANET) |
| Der eine Swing-Trade | ✅ OSCR: Momentum-Runner 24 Tage gehalten → grösster Gewinner. Genau das Playbook-Muster |

## Counterfactual: Playbook mechanisch auf dieselben Entries

| Trade | Sein Ergebnis | Playbook (Struct-Stop, 3R, set-and-forget) |
|---|---|---|
| NFLX | +47 | ~−83 (Stop 6/16 gerissen, NFLX fiel −13 %) |
| OSCR | +778 | ~+780 (identisch gut, liefe noch) |
| NVDA | +1 (BE) | ~−64 (Struct-Stop 6/23 gerissen) |
| TSM | −245 | ~−320 unrealisiert (Stop nie erreicht, Position −4 %) |
| GOOGL | +41 | ~−1R (GOOGL fiel nach seinem Exit auf 330) |
| AMD | +700 | ~−440 unrealisiert (AMD −6.3 % seit Entry; er verkaufte in der Tageshoch-Zone) |
| **Summe** | **+1'322** | **grob −130 bis +650** |

**Der Monat Juni 2026 war ein Chop-/Extended-Markt** (TSM/AMD/NVDA-Whipsaws,
NFLX/GOOGL-Einbrüche). In genau diesem Regime verlieren mechanische
Breakout-Systeme laut unseren eigenen Jahres-Splits (2015/2018-Analogie) —
und die diskretionären Schnell-Exits des Users haben es besser gehandhabt.

## Ehrliche Einordnung (beide Richtungen)

1. **Nicht daraus schliessen „diskretionär > systematisch".** n=6
   Counterfactuals in einem Monat; der AMD-Verkauf 0.6 % unter Tageshoch ist
   nicht regelhaft wiederholbar; und im Backtest über 397 Trades gewinnt
   Halten klar. Ein Monat beweist nichts — in beide Richtungen.
2. **Aber auch nicht ignorieren:** Die Schnell-Exits waren hier kein Zufall
   über 6 unabhängige Titel — sie passten zum Regime. Das stützt die
   Playbook-Regel R2 (Regime-Filter): In EXTENDED/Chop-Phasen keine neuen
   mechanischen Breakout-Positionen.
3. **Das reale Risiko liegt woanders:** 133 %-Positionen (HOOD) mit
   0.06 %-Stops sind Tail-Risk-Bomben — ein Gap durch den Stop (Halt,
   News) kostet zweistellige Kontoprozente. Der starke Monat hängt an
   2 Trades; die Methode ist auf Dauerbelastung nicht getestet.
4. **PDT-Grenze:** Konto < 25k USD + Daytrading-Frequenz = Zwangsbremse.
   Entweder Konto aufstocken, Frequenz senken (Swing gemäss Playbook) oder
   bewusst mit 3 Daytrades/5 Tage leben.

## Empfehlungen

1. **Risiko-Deckel sofort:** Max. 1 % Kontorisiko pro Trade (Stop-Distanz ×
   Grösse), max. 100 % Brutto-Exposure. Der Edge des Monats überlebt auch
   mit halber Grösse; ein HOOD-Gap nicht.
2. **Journal in R:** Vor jedem Entry Stop definieren → jedes Ergebnis in R
   notieren. Erst damit wird messbar, ob die diskretionären Exits Skill
   oder Juni-Glück sind. Nach 40 Trades wissen wir es.
3. **Zweigleisig fahren:** Die OSCR-Klasse (Playbook-konforme Swing-Runner,
   klein & selten angefasst) vom Daytrading-Konto trennen — mental oder
   real. Der eine Swing-Trade hat mehr verdient als 12 Daytrades zusammen.
4. **Limits streichen** (die eigene Regel!): NVDA/GOOGL/SNEX/HOOD waren
   Limit-Käufe in Schwäche — zwei davon direkt vor weiteren Einbrüchen.
