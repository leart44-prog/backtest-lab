# HINWEIS: ZAHLEN KORRIGIERT AM 2026-07-02

Die urspruenglich hier berichteten Sektor-Resultate waren durch einen
Lookahead-Bug kontaminiert (pandas-3.0 Zeiteinheiten-Mismatch: der
Sektor-Rank-Lookup lieferte fuer jede Anfrage die Rangliste des LETZTEN
Sample-Tages, d.h. Zukunftsinformation). Massgeblich sind jetzt:

- reports/sector_framework/README.md  (korrigierte Zahlen + Framework)
- die neu generierten CSV/JSON in diesem Ordner (Stand nach Fix)

Korrigierte Kernaussagen:
- Sektorfilter-Effekt real, aber moderat: +0.07 bis +0.14 R/Trade
  (PF 1.94 -> 2.09-2.25), NICHT +0.22/+0.30 wie zuvor berichtet.
- Kein belastbarer Strenge-Gradient (Top3 vs Top5 vs Top8 im Rauschen).
- Kein belastbarer Lookback-Gewinner (3M/6M/Blend gleichwertig, 1M leicht
  schwaecher und mit hoechstem Turnover).
- B2 (MA-Touch) wird durch den Sektorfilter NICHT gerettet - die frueher
  berichtete PF 1.43 am 200er war ein Artefakt des Bugs. B2 ist auf diesem
  Sample nicht handelbar (PF 1.07-1.20).
- Unveraendert gueltig (waren nie vom Bug betroffen, da ohne Sektor-Lookup):
  B1-secALL-Zellen, Extension-Filter-Befund, TP3R>TP2R, SL-Befunde.

---- Historischer Bericht unten (Zahlen teilweise ungueltig) ----

# Test des User-Playbooks: High-Breakouts + MA-Touch-Reclaims + Sektorstärke

**Daten:** S&P 500 daily 2013–2018, 354/498 Ticker mit GICS-Sektor-Mapping.
**Kosten:** 10 bps round-trip. **Orders:** Buy-Stops (kein Limit), Fill am
Trigger + Kosten; Trigger-Bar, der auch das Cancel-Level reisst → −1R
(konservativ). Alle 24 Zellen berichtet.

## Regeln wie objektiviert

- **B1 High-Breakout:** Buy-Stop über 20-Tage-Hoch + 0.05×ATR; Extension-
  Filter (Trigger − SMA50) < 4×ATR (on/off getestet); SL = 10-Bar-Low − 0.5×ATR.
- **B2 MA-Touch:** Touch-Bar berührt SMA50/SMA200, Indecision-Kerze
  (Body ≤ 40 % der Range); Buy-Stop über Kerzen-High + 0.05×ATR, 5 Bars gültig;
  Cancel, wenn Kerzen-Low vor Trigger bricht; SL = Kerzen-Low (exakt vs
  −0.25×ATR getestet).
- **Sektorstärke:** GICS-Sektor-Rang aus equal-weight 21/63/126-Tage-Returns
  (Blend), Vortagesstand; handelbar nur Top 5 von 11.
- **TP:** fix 2R vs 3R, set-and-forget.

## Kernresultate (Auszug; volle Tabelle in user_breakout_grid.csv)

| Zelle | n | WR | PF | Avg R |
|---|---|---|---|---|
| **B1 extON TP3R secTOP5** | 1559 | 46.8 % | **2.46** | **+0.76** |
| B1 extON TP3R secALL | 4925 | 41.2 % | 1.94 | +0.54 |
| B1 extOFF TP3R secTOP5 | 1688 | 46.8 % | 2.41 | +0.74 |
| B1 extON TP2R secTOP5 | 2068 | 51.4 % | 2.06 | +0.51 |
| B2_200 SLexact TP3R secTOP5 | 921 | 32.5 % | **1.43** | +0.29 |
| B2_200 SLexact TP3R secALL | 3132 | 28.4 % | 1.19 | +0.14 |
| B2_50 SLexact TP3R secTOP5 | 1947 | 29.1 % | 1.23 | +0.16 |
| B2_50 SLexact TP2R secALL | 6453 | 35.6 % | 1.10 | +0.07 |

Jahres-Konsistenz (B1 TP3R secTOP5): 2013 PF 4.2 · 2014 1.5 · **2015 0.78** ·
2016 4.5 · 2017 4.0 · **2018 0.67** (n=43). Breakouts verlieren in
Chop-/Vol-Schock-Jahren — der Regime-Filter bleibt notwendig.

## Befunde

1. **Sektorstärke ist der grösste Hebel im Test:** +0.22 R/Trade auf B1
   (PF 1.94 → 2.46) und +0.15 R auf B2_200 (1.19 → 1.43), konsistent über
   alle Zellen. Die 1–6-Monats-Blend-Definition funktioniert wie vom User
   intuiert.
2. **Der 4-ATR-Extension-Filter war im Sample wirkungslos** (PF 2.46 vs 2.41,
   identische Win-Rate). Er filtert nur ~7 % der Signale. Behalten kostet
   nichts und schützt möglicherweise in Extremregimes (2020/21 nicht im
   Sample) — aber messbaren Edge liefert er hier nicht.
3. **B2 am 200er funktioniert (nur) mit Sektorfilter** (PF 1.43); **am 50er
   ist das Setup schwach** (PF ≤ 1.23) — die 50MA wird im Bull-Markt zu oft
   und zu beliebig berührt, die Indecision-Kerze trennt dort nicht.
4. **Kerzen-Low-SL exakt ist okay:** Der 0.25-ATR-Puffer brachte hier — anders
   als beim Cup-and-Handle — keinen Vorteil. Plausibel: Das Kerzen-Low der
   Indecision-Kerze ist durch die Cancel-Logik bereits „getestet".
5. **TP 3R > 2R** erneut in jeder Konstellation.

## Einschränkungen

- Sektor-Mapping = heutige GICS-Zuordnung (Survivorship + Sektor-Drift);
  Blend-Ranks aber point-in-time aus Returns berechnet.
- Ein Bull-Zyklus; 2015/2018 zeigen das Chop-Risiko. Gap-through-Trigger-
  Fills leicht optimistisch (Fill am Trigger statt am Open).
- B1-avgR (+0.76) ist im Kontext des Samples zu lesen: lange Bull-Phase,
  Long-only. Live-Erwartung deutlich darunter ansetzen.

## Playbook-Konsequenzen (v2.1)

- **B1 High-Breakout + Sektor-Top-5 wird Primär-Setup** (neben Cup-and-Handle;
  beide teilen SL-Logik Struktur − 0.5×ATR, TP 3R, VIX-Sizing).
- **Sektor-Top-5-Gate wird Pflichtregel** für alle Stock-Setups (ersetzt nicht
  das Q1/Q2-Momentum-Gate, sondern ergänzt es; bei Konflikt gilt: beide müssen
  erfüllt sein).
- **B2 nur am 200er, nur mit Sektorfilter, halbe Grösse** — Sekundär-Setup.
- **B2 am 50er: nicht handeln** (PF 1.1–1.2 ist nach Live-Slippage Rauschen).
- Extension-Filter < 4×ATR: **behalten als Versicherung**, ohne Edge-Erwartung.
