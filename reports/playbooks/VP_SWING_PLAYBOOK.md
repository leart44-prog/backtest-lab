# Swing-Playbook: Limit-Orders, S/D-Zonen & Volumenprofile (v1.0)

Stand 2026-08. Jede Regel trägt einen Evidenz-Tag:
**[BELEGT]** = in mehreren unabhängigen Tests dieser Session bestätigt
(inkl. Datenquellen-/Ären-Replikation) · **[EXPLORATIV]** = klares
Muster, aber nachträglich gefunden — erst prospektiv bestätigen ·
**[KONVENTION]** = Festlegung ohne Edge-Anspruch ·
**[NEGATIV-BELEGT]** = getestet und verworfen; nicht handeln.

---

## Teil 0 · Das Verdikt zu Volumenprofilen — zuerst, weil du danach gefragt hast

**V1. Keine Limit-Orders an Weekly-/Monthly-Profilkanten.** [NEGATIV-BELEGT]
28 Paare, 23 Jahre, echte Tick-Volumen-Profile, 9 deklarierte Zellen:
PF 0.39–0.84 mit Kosten, **0.53–0.96 ohne Kosten** — jede Zelle unter
Breakeven, beide Ären, Long wie Short. Weekly-Kanten sind die
schlechtesten getesteten Entry-Levels der gesamten Session.

**V2. VP-Konfluenz ist kein Zonen-Filter.** [NEGATIV-BELEGT]
S/D-Zonen an Profilkanten: PF 0.87–0.92 vs. 0.91–0.92 ohne. Nähe zu
VAL/VAH macht eine Zone nicht besser.

**V3. Erlaubte VP-Nutzung: Kontext, nicht Trigger.** [KONVENTION]
POC/VA als Landkarte fürs eigene Verständnis (wo ist Akzeptanz, wohin
kann es rotieren) ist unschädlich — aber keine Regel dieses Playbooks
hängt davon ab, und kein Trade wird wegen eines VP-Levels genommen
oder verworfen.

---

## Teil 1 · Das Setup (die einzige Konfiguration mit positiver Evidenz)

**R1 · Markt & Timeframe: FX-Paare, Tageschart.** [BELEGT]
Der Edge existiert nur in FX (Klassen-Split: FX PF 2.15 vs.
Indizes/Metalle 0.21) und nur auf Daily (4H: Richtung repliziert, Marge
kollabiert auf ~1.0–1.26, quellen-inkonsistent). Universum: möglichst
breit (21 Crosses + 7 Majors), gleiche Regeln überall.

**R2 · Zone: frische Umkehrzone.** [BELEGT]
v5-Synthese-Zonen, nur Formationen DBR (Drop-Base-Rally, Demand) und
RBD (Rally-Base-Drop, Supply). Frisch = 0 bisherige Touches. Zonen-Alter
maximal ~60–100 Tage — die genaue Zahl ist egal (Plateau), "jung schlägt
alt" ist das robuste Muster.

**R3 · Valuation-Extrem als Pflicht-Gate.** [BELEGT]
Long an Demand nur bei Valuation-Score ≤ −t1, Short an Supply nur bei
≥ +t1 (dein v6-Indikator, FX-Schwelle 60), gelesen am letzten
ABGESCHLOSSENEN Tag. Ohne dieses Gate ist die Zonen-Familie in jedem
Test Breakeven bis negativ.

**R4 · Richtung: gegen die Hochzins-Währung.** [BELEGT]
Nur Trades, die GEGEN die aktuell höher verzinste Währung des Paares
gerichtet sind (Long die Niedrigzins-Basis an Demand / Short die
Hochzins-Basis an Supply). Gegen-Carry: PF 1.62 (vor 2013) / 1.72
(danach); mit Carry: 0.78–1.10. In 16/16 Zellen des 4H-Tests bestätigte
sich die Richtung. Die Umkehrung — mit der Hochzins-Währung — ist
verboten. [NEGATIV-BELEGT]

**R5 · Regime-Ampel (Leitzins).** [EXPLORATIV]
Grün: US-Leitzins unten angekommen und gehalten (Hold-tief: PF 1.95;
in nie fürs Tuning benutzten Jahren 1.84) UND Paar-Differential seit
~12 Monaten stabil (<0.5 % Änderung: PF 1.47 vs. 0.95). Rot:
Zins-Plateau oben (Hold-hoch: PF 0.28, alle drei Phasen zweier
Jahrzehnte negativ). Gelb (Senkungs-/Anhebungszyklen): halbe Grösse
oder aussetzen. Stand Aug 2026: Senkungszyklus = GELB.

**R6 · Entry: Limit-Order an der Preferred-Proximal-Kante.** [BELEGT]
Genau an der Kante (Body-Extrem der Base). Limit tiefer in die Zone
legen verschlechtert: 25 %/50 % Tiefe → PF 0.74/0.63, Winrate FÄLLT
auf 21–23 %. [NEGATIV-BELEGT] Bei gestapelten Zonen die distale nehmen.

**R7 · Stop & Ziel: SL 25 % der Zonenhöhe hinter Distal, TP fix ~3R,
nichts anfassen.** [BELEGT]
TP-Kurve monoton steigend bis 3–4R (1:1 ist selbst auf der besten Zelle
negativ), Rollover nach 5R; 3R ist der ära-stabilste Punkt. Verboten:
Break-even-Stops (PF 1.05→0.71), Partials, Trailing vor 3R, enge Ziele.
[NEGATIV-BELEGT, 5× repliziert]

**R8 · Risiko & Frequenz.** [KONVENTION]
0.5–1.0 % Risiko pro Trade, 1 Position pro Paar, korrelierte Paare
(gleiche Basis-/Quotewährung) nicht stapeln. Erwartung: ~2–3 Trades
pro JAHR übers ganze Universum, ØR ~+0.4–0.55 bei 3R-Ziel. Das ist ein
Geduldssystem — mehr Trades erzwingen = Filter verwässern = Edge weg.

**R9 · Verbotsliste (alles getestet, alles tot).** [NEGATIV-BELEGT]
Weekly/Monthly-VP-Kanten als Entry · VP-Konfluenz als Filter · 4H- oder
1H-Ausführung · Indizes/Metalle mit diesem Setup · tiefere Limits ·
BE/Partials/enge TPs · LoL-Zonen bevorzugen · HTF-Coverage als Pflicht ·
Trades mit der Hochzins-Währung · "beste Paare" selektieren.

---

## Teil 2 · Ehrlichkeits-Kasten

1. Die Kombination R2+R3+R4 ist gestapelt aus nachträglich gefundenen
   Filtern. Für sie spricht: Ären-Stabilität (1.62/1.72), Quellen-
   Replikation, plausibler Mechanismus, 16/16-Richtungskonsistenz.
   Gegen sie: n≈56 auf Daily, Selektionsrisiko. **Konsequenz: klein
   handeln und die ersten 20–30 Live-Trades als prospektiven Test
   führen; erst danach Grösse.**
2. R5 (Regime) ist explorativ — als Ampel nutzen, nicht als Gewissheit.
3. Nichts in diesem Playbook ist eine Gewinngarantie. Die Basis-Familie
   (Zonen ohne Gates) ist nach ehrlicher Messung ein Nullsummenspiel
   minus Kosten — der gesamte Anspruch liegt in den Gates R3–R5.
