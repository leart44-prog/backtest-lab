# Detektor-Shootout auf DAILY: Course vs v4 vs v5-Synthesis

Gleiche auditierte Engine, gleiches Management (Limit@Proximal, SL 25 %
hinter Distal, TP 2.5R, frisch/1-Touch-25 %), gleiche Kosten, gleiche
Valuation — **nur der Detektor wechselt.** v5-Parameter wurden vor dem
Lauf deklariert. 40 Instrumente, Daily, 2013–2026.

## Ergebnisse (Profit Factor, n in Klammern)

| Detektor | BASE | + Valuation | + Val & frisch |
|---|---|---|---|
| Course-Method | 0.92 (5'950) | **1.04** (122) | 1.02 (100) |
| v4 | 0.92 (7'037) | 0.97 (203) | 1.00 (161) |
| **v5 Synthesis** | 0.91 (6'887) | 1.00 (193) | **1.05** (146) |
| v5 nur LoL-Zonen | — | **0.87** (95) | — |

IS/OOS-Muster überall gleich: IS 0.76–0.92, OOS 1.16–1.35 (Valuation-Configs).

## Befunde

1. **„Der Indikator ist schuld" ist widerlegt.** Drei strukturell
   verschiedene Detektoren (Body%-Range-Logik, ATR+Wick-Logik, Synthese)
   liefern auf Basis-Ebene praktisch identische Resultate (PF 0.91–0.92
   bei n≈6–7k). Der Engpass ist nicht die Zonen-Erkennung, sondern das
   Konzept „erster Retest einer Zone" selbst.
2. **Die Valuation-Zellen aller Detektoren liegen bei Breakeven**
   (0.97–1.05); die Differenzen zwischen den Detektoren (±0.04) sind bei
   n=100–200 Rauschen. Kein Detektor ist belastbar „der beste" — v5
   (VAL+frisch: 1.05, OOS 1.35) und Course (VAL: 1.04) sind nominell vorn.
3. **LoL ist KEIN Qualitätsmerkmal — im Gegenteil.** LoL-Zonen (überlappend/
   ≤0.5 ATR nahe) performen deutlich schlechter als der v5-Durchschnitt
   (PF 0.87 vs 1.00). Plausibler Mechanismus: gestapelte Zonen markieren
   Congestion-Bereiche, durch die der Preis sich durchfrisst. Der neue
   Indikator zeigt LoL als Information an — mit Warnhinweis im Tooltip.
4. Frequenz der besten Zellen: 0.2–0.4 Trades/Woche übers 40er-Universum.

## Konsequenz

Der neue v5-Indikator (indicators/sd_zones_v5_synthesis.pine) ist so gut
wie die beiden Vorgänger und sauberer konstruiert (Preferred/Wider,
LoL-Anzeige, kein Repainting, kurze Bases) — aber die ehrliche Kernaussage
bleibt: Die Zonen-Detektion war nie das Problem. Wer diese Strategie-Familie
weiterentwickeln will, muss am Konzept arbeiten (wann ein Retest handelbar
ist — Arrival, Valuation, Regime), nicht an der Zonen-Geometrie.
