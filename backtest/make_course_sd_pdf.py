"""Generate the OTC-style PDF report for the course S/D + valuation study."""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "reports", "course_sd")
PDF_PATH = os.path.join(REPORT_DIR, "SD_Course_Valuation_Zone_Study.pdf")

DARK = "#1a2332"
ACCENT = "#2c7fb8"
RED = "#c0392b"
GREEN = "#27ae60"


def _table_page(pdf, title, subtitle, col_labels, rows, row_colors=None, notes=None):
    fig = plt.figure(figsize=(11.7, 8.3))
    fig.patch.set_facecolor("white")
    fig.text(0.06, 0.93, title, fontsize=20, fontweight="bold", color=DARK)
    fig.text(0.06, 0.885, subtitle, fontsize=11, color="#555555")
    ax = fig.add_axes([0.06, 0.16, 0.88, 0.66])
    ax.axis("off")
    tbl = ax.table(cellText=rows, colLabels=col_labels, loc="upper center",
                   cellLoc="center")
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9.5)
    tbl.scale(1, 1.55)
    for (r, c), cell in tbl.get_celld().items():
        cell.set_edgecolor("#dddddd")
        if r == 0:
            cell.set_facecolor(DARK)
            cell.set_text_props(color="white", fontweight="bold")
        elif row_colors and r - 1 < len(row_colors) and row_colors[r - 1]:
            cell.set_facecolor(row_colors[r - 1])
    if notes:
        fig.text(0.06, 0.06, notes, fontsize=9, color="#555555", va="bottom",
                 wrap=True)
    pdf.savefig(fig)
    plt.close(fig)


def main():
    with open(os.path.join(REPORT_DIR, "course_sd_results.json")) as f:
        res = json.load(f)

    with PdfPages(PDF_PATH) as pdf:
        # ── Cover ──
        fig = plt.figure(figsize=(11.7, 8.3))
        fig.patch.set_facecolor(DARK)
        fig.text(0.5, 0.66, "Supply & Demand Zone Study", ha="center",
                 fontsize=30, fontweight="bold", color="white")
        fig.text(0.5, 0.58, "Course Method (RBR/DBR/RBD/DBD)  ×  Valuation Score",
                 ha="center", fontsize=16, color="#9fc5e8")
        fig.text(0.5, 0.47,
                 "40 Instrumente · Forex Majors & Crosses, Indizes, Metalle, Energien\n"
                 "4H-Daten 2013–2026 · ehrliche Fills · Kosten & Kommission\n"
                 "6 vorab deklarierte Konfigurationen · 3-Agenten-Code-Audit",
                 ha="center", fontsize=12, color="#cccccc")
        fig.text(0.5, 0.30, "Backtest Lab — kritische Quant-Analyse\nJuli 2026",
                 ha="center", fontsize=11, color="#888888")
        pdf.savefig(fig)
        plt.close(fig)

        # ── Methodology ──
        fig = plt.figure(figsize=(11.7, 8.3))
        fig.text(0.06, 0.93, "Methodik & Regeln", fontsize=20, fontweight="bold", color=DARK)
        meth = (
            "ZONEN (1:1-Port des Pine-Indikators 'Course Method')\n"
            "  •  Leg-in → Base (1–6 indecisive Kerzen) → Leg-out (explosiv/decisive-gross/Gap ≥ 1.5×AvgRange)\n"
            "  •  Proximal = Body-Extrem der Base (Preferred), Distal inkl. Leg-out-Extrem · Speed-Bump-Filter aktiv\n"
            "  •  Zonen entstehen nur auf abgeschlossenen Bars — kein Repainting\n\n"
            "TRADE-MANAGEMENT (User-Vorgabe)\n"
            "  •  Limit-Order am Preferred-Proximal · SL = 25% der Zonenhöhe hinter dem Distal · TP fix 2.5R\n"
            "  •  Frische: nur unberührte Zonen oder max. 1 Touch mit ≤ 25% Penetration\n"
            "  •  Gestapelte Zonen: nur die distale (tiefere) · 1 Position pro Instrument\n\n"
            "VALUATION-GATE (1:1-Port 'Valuation Score', Hybrid-Modus)\n"
            "  •  FX: echte Futures-Ratios (6E/6B/6A/6N/6C/6S/6J), USD-Legs = 1.0 — exakt wie im Original\n"
            "  •  Indizes/Metalle/Energien: Equal-Weight-Klassen-Basket als Benchmark (ZB/GC-Daten nicht verfügbar\n"
            "     — dokumentierte Abweichung vom Original)\n"
            "  •  Long nur bei Score ≤ −t1 (undervalued), Short nur bei ≥ +t1 · t1 = 60 (Crosses) / 70 (Majors) / 80 (Rest)\n\n"
            "HTF-COVERAGE (Confluence-Test)\n"
            "  •  Daily-Zonen mit demselben Detektor · LTF-Zone muss in gleichgerichteter aktiver Daily-Zone liegen\n"
            "  •  Nur vollständig abgeschlossene Tages-Bars zählen (Audit-Fix gegen Lookahead)\n\n"
            "EHRLICHKEITS-REGELN\n"
            "  •  Same-Bar-Stop-Out = −1R (Limit-Order-Realität) · Stop-vor-Target intrabar · Spread+Slippage+Kommission\n"
            "  •  Alle Gates lesen nur Daten des letzten abgeschlossenen Bars · 3-Agenten-Audit vor Interpretation"
        )
        fig.text(0.06, 0.86, meth, fontsize=10.5, color="#333333", va="top", family="monospace")
        pdf.savefig(fig)
        plt.close(fig)

        # ── Config matrix results ──
        cols = ["Konfiguration", "Trades", "Trades/Woche", "Win-Rate", "Profit Factor",
                "Avg R", "IS PF", "OOS PF"]
        rows, colors = [], []
        labels = {
            "C1_BASE": "C1  Zonen pur (User-Management)",
            "C2_VAL": "C2  + Valuation-Gate",
            "C3_HTF": "C3  + HTF-Coverage",
            "C4_VAL_HTF": "C4  + Valuation + HTF",
            "C5_FRESH": "C5  Valuation + nur frische Zonen",
            "C6_VALSTRONG": "C6  Valuation streng (t1+15)",
        }
        for k, lab in labels.items():
            r = res[k]
            a = r["all"]
            rows.append([lab, a["n"], r.get("trades_per_week", "—"),
                        f"{a.get('wr', 0) * 100:.1f}%", a.get("pf", "—"),
                        f"{a.get('avg_r', 0):+.3f}",
                        r["IS"].get("pf", "—"), r["OOS"].get("pf", "—")])
            pf = a.get("pf") or 0
            colors.append("#fdecea" if pf < 1 else "#eafaf1")
        _table_page(pdf, "Ergebnis-Matrix — alle Konfigurationen",
                    "Alle Zellen berichtet. Kein Cherry-Picking. IS = 2013–2020, OOS = 2021–2026.",
                    cols, rows, colors,
                    notes="Hinweis: Ein früherer Lauf zeigte für C4 PF 3.33 — verursacht durch zwei im Audit "
                          "gefundene Bugs (toter FX-Valuation-Score durch Timestamp-Mismatch; HTF-Coverage las den "
                          "laufenden Tages-Bar = Lookahead, gemessen +0.21R/Trade). Diese Tabelle zeigt die "
                          "korrigierten, ehrlichen Zahlen.")

        # ── Per-class table (best config C5/C2) ──
        for key, title in (("C2_VAL", "C2 — Zonen + Valuation-Gate"),
                           ("C5_FRESH", "C5 — Valuation + nur frische Zonen")):
            bc = res[key]["by_class"]
            cols2 = ["Asset-Klasse", "Trades", "Win-Rate", "Profit Factor", "Avg R", "Sum R"]
            rows2, colors2 = [], []
            for klass in ("fx_major", "fx_cross", "indices", "metals", "commodities"):
                if klass not in bc:
                    continue
                s = bc[klass]
                rows2.append([klass, s["n"], f"{s.get('wr', 0) * 100:.1f}%",
                             s.get("pf", "—"), f"{s.get('avg_r', 0):+.3f}", s.get("sum_r", 0)])
                pf = s.get("pf") or 0
                colors2.append("#fdecea" if pf < 1 else "#eafaf1")
            _table_page(pdf, f"Aufschlüsselung: {title}",
                        "Pro Asset-Klasse (Struktur wie OTC Zone Studies)", cols2, rows2, colors2)

        # ── Equity curves ──
        fig, ax = plt.subplots(figsize=(11.7, 8.3))
        for k, col in (("C1_BASE", "#999999"), ("C2_VAL", ACCENT), ("C5_FRESH", GREEN),
                       ("C3_HTF", RED)):
            path = os.path.join(REPORT_DIR, f"{k}_trades.csv")
            if not os.path.exists(path):
                continue
            t = pd.read_csv(path, parse_dates=["ts"])
            t = t.sort_values("ts")
            ax.plot(t["ts"], t["r"].cumsum(), label=f"{labels[k]}", color=col, linewidth=1.4)
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_title("Kumulierte R über Zeit (0.5% Risiko pro Trade ≙ R-Skala)",
                     fontsize=15, fontweight="bold", color=DARK)
        ax.legend(fontsize=10)
        ax.grid(alpha=0.3)
        pdf.savefig(fig)
        plt.close(fig)

        # ── Verdict ──
        fig = plt.figure(figsize=(11.7, 8.3))
        fig.text(0.06, 0.93, "Fazit — Go / No-Go", fontsize=20, fontweight="bold", color=DARK)
        verdict = (
            "ERGEBNIS: NO-GO für den Live-Einsatz in der getesteten Form.\n\n"
            "1.  Keine der 6 Konfigurationen ist nach ehrlichen Fills und Kosten profitabel (PF 0.75–0.88).\n"
            "    Der Basis-Detektor produziert ~44 Signale/Woche mit PF 0.81 — die Zonen selbst tragen\n"
            "    auf 4H keinen messbaren Edge.\n\n"
            "2.  Das Valuation-Gate ist der beste Filter im Test: PF 0.81 → 0.87/0.88 (C2/C5), OOS besser\n"
            "    als IS (0.91/0.92). Richtung stimmt — aber es hebt die Strategie nicht über Wasser und\n"
            "    drückt die Frequenz auf ~0.8–0.9 Trades/Woche (Ziel war 2–3).\n\n"
            "3.  HTF-Coverage verschlechtert das Ergebnis (PF 0.78) — nach dem Lookahead-Fix. Der scheinbar\n"
            "    starke Confluence-Effekt des ersten Laufs war vollständig ein Datenleck.\n\n"
            "4.  Frequenz-Ziel 2–3 Trades/Woche und Profitabilität stehen im Konflikt: Jede Verschärfung,\n"
            "    die die Qualität hebt, senkt die Frequenz unter das Ziel.\n\n"
            "WAS AM EHESTEN WEITERHILFT (evidenzbasiert aus dieser Session):\n"
            "  •  Stop-Entries statt Limit-Orders am Proximal: im paired Test +0.12 bis +0.21 R/Signal —\n"
            "     würde die Lücke verkleinern, nach Extrapolation aber nicht schliessen.\n"
            "  •  Valuation-Score als eigenständiges Mean-Reversion-Signal testen (ohne Zonen-Trigger).\n"
            "  •  Höhere Timeframes (Daily-Zonen als Entry-TF) — weniger Rauschen pro Zone.\n\n"
            "TRANSPARENZ: Ein 3-Agenten-Audit fand vor der Interpretation 2 kritische Bugs (toter\n"
            "FX-Score, HTF-Lookahead) und 4 kleinere. Alle Zahlen in diesem Report sind nach den Fixes\n"
            "gerechnet. Der Wunsch, 'so lange zu testen, bis ein Edge entsteht', wurde bewusst nicht\n"
            "durch Data-Mining erfüllt — ein durch Suchen erzwungener Edge wäre im Live-Einsatz wertlos."
        )
        fig.text(0.06, 0.86, verdict, fontsize=11, color="#333333", va="top", family="monospace")
        pdf.savefig(fig)
        plt.close(fig)

    print(f"Saved {PDF_PATH}")


if __name__ == "__main__":
    main()
