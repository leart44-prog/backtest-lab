# Weekly/Monthly-Volume-Profile-Studie (Limit-Orders an Profilkanten)

Frage des Users: Swingtrading mit Limit-Orders an Supply/Demand-Levels
aus Weekly- und Monthly-Volumenprofilen. Deklarierter Rahmen vor dem
Lauf; alle Zellen berichtet.

**Daten:** Dukascopy 1H mit Tick-Volumen, 28 FX-Paare (21 Crosses + 7
Majors), 2003–2026. Profile volumengewichtet (Bar-Volumen gleichmässig
über die berührten Preis-Bins verteilt), kalender-verankert, kausal (ein
Bar nutzt ausschliesslich das Profil der letzten ABGESCHLOSSENEN Woche
bzw. des letzten abgeschlossenen Monats), Bin 0.10× Perioden-ATR,
Value Area 70 %. Ausführung Daily, ehrliche Fills (Same-Bar-Stopout =
−1R, SL vor TP, EOS zum Close), Kosten, 1 Position/Paar, Ära-Split 2013.

## Familie A — Limit an der Profilkante (VAL long / VAH short)

Fill nur bei Anlauf von der richtigen Seite (Vortages-Close jenseits der
Kante), erster Touch je Periode+Seite, SL = 25 % der VA-Höhe hinter der
Kante.

| Zelle | n | WR | PF (Kosten) | PF (kostenlos) | vor/nach 2013 |
|---|---|---|---|---|---|
| W · TP POC | 29'477 | 21.5 % | 0.39 | 0.53 | 0.40 / 0.38 |
| W · TP Gegenkante | 27'570 | 16.1 % | 0.60 | 0.77 | 0.62 / 0.58 |
| W · TP 2.5R | 29'100 | 19.1 % | 0.54 | 0.63 | 0.56 / 0.52 |
| M · TP POC | 7'949 | 31.6 % | 0.71 | 0.84 | 0.78 / 0.67 |
| M · TP Gegenkante | 7'335 | 19.4 % | 0.84 | **0.96** | 0.92 / 0.80 |
| M · TP 2.5R | 7'879 | 25.7 % | 0.82 | 0.94 | 0.91 / 0.78 |

**Selbst ohne jegliche Kosten bleibt jede Zelle unter Breakeven.**
Weekly-Kanten sind brutto tief negativ (0.53–0.77) — der Preis, der eine
Wochen-Value-Area-Kante erreicht, läuft überproportional weiter statt
zu drehen. Monthly ist brutto nahe Zufall (0.84–0.96) und netto klar
negativ. Long/Short symmetrisch schlecht, beide Ären schlecht.

## Familie B — VP-Konfluenz als Zonen-Filter

v5-S/D-Zonen (frisch, First Touch, TP 2.5R, ohne Valuation), gesplittet
nach Nähe des Proximal zur passenden Profilkante (≤ 0.30× VA-Höhe):

| Split | mit Konfluenz | ohne Konfluenz |
|---|---|---|
| Weekly-Kante | 0.87 (n=936) | 0.92 |
| Monthly-Kante | 0.92 (n=1'089) | 0.91 |
| eine von beiden | 0.88 (n=1'847) | 0.92 |

**VP-Nähe verbessert Zonen-Trades nicht** — Weekly-Konfluenz ist sogar
nominal schlechter. Konsistent mit der ersten Studie dieser Session
(TPO-Profile auf Repo-Daten: ebenfalls kein Edge).

## Fazit

Mechanische Limit-Orders an W/M-Volumenprofilkanten haben auf FX-Daily
keinen Edge — nicht brutto, nicht netto, in keiner Ära, weder als
eigenständiges Setup noch als Konfluenz-Filter für S/D-Zonen. Bei
n=7'000–29'000 pro Zelle ist das kein Stichprobenproblem. Playbook:
`reports/playbooks/VP_SWING_PLAYBOOK.md`.
