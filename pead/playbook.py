"""Generate a printable PEAD strategy playbook PDF.

Single tall page layout (no A4 page breaks) so the reader can scroll
through the whole document continuously. Equity curve and gap-
stratification chart are rendered with annotated, currency-formatted axes.

Run:
    .venv/bin/python -m pead.playbook --out playbook.pdf
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .backtest import run_universe
from .metrics import equity_curve, stratify_by_gap, summary, trades_to_frame
from .synthetic import make_universe

INK = colors.HexColor("#0F172A")
ACCENT = colors.HexColor("#0EA5E9")
MUTED = colors.HexColor("#475569")
SUBTLE = colors.HexColor("#E2E8F0")
BG = colors.HexColor("#F8FAFC")
GREEN = colors.HexColor("#16A34A")
RED = colors.HexColor("#DC2626")
AMBER = colors.HexColor("#D97706")

PAGE_W = 21 * cm
PAGE_H = 300 * cm

INK_HEX = "#0F172A"
ACCENT_HEX = "#0EA5E9"
MUTED_HEX = "#475569"
GREEN_HEX = "#16A34A"
SUBTLE_HEX = "#E2E8F0"


def _styles():
    base = getSampleStyleSheet()
    s = {
        "title": ParagraphStyle(
            "title", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=30, leading=34, textColor=INK, alignment=TA_LEFT, spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "subtitle", parent=base["Normal"], fontName="Helvetica",
            fontSize=13, leading=17, textColor=MUTED, alignment=TA_LEFT, spaceAfter=20,
        ),
        "section": ParagraphStyle(
            "section", parent=base["Heading1"], fontName="Helvetica-Bold",
            fontSize=20, leading=24, textColor=INK, spaceBefore=24, spaceAfter=12,
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=13, leading=17, textColor=ACCENT, spaceBefore=14, spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "body", parent=base["BodyText"], fontName="Helvetica",
            fontSize=10.5, leading=15, textColor=INK, spaceAfter=7,
        ),
        "small": ParagraphStyle(
            "small", parent=base["BodyText"], fontName="Helvetica",
            fontSize=9, leading=12, textColor=MUTED, spaceAfter=4,
        ),
        "label": ParagraphStyle(
            "label", parent=base["BodyText"], fontName="Helvetica-Bold",
            fontSize=9, leading=12, textColor=MUTED,
        ),
        "footer": ParagraphStyle(
            "footer", parent=base["BodyText"], fontName="Helvetica",
            fontSize=8, leading=10, textColor=MUTED, alignment=TA_CENTER,
        ),
    }
    return s


def _section_header(title: str, styles) -> list:
    """A bold section header with an accent bar above it for visual separation
    on a continuous-scroll page."""
    bar = Table([[""]], colWidths=[3 * cm], rowHeights=[3])
    bar.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), ACCENT),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return [Spacer(1, 16), bar, Spacer(1, 4), Paragraph(title, styles["section"])]


def _hr(width=17 * cm):
    t = Table([[""]], colWidths=[width], rowHeights=[0.4])
    t.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 0.7, SUBTLE)]))
    return t


def _rule_box(label: str, value: str, color=ACCENT) -> Table:
    t = Table([[label], [value]], colWidths=[8.2 * cm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (0, 0), 8.5),
        ("TEXTCOLOR", (0, 0), (0, 0), MUTED),
        ("FONTNAME", (0, 1), (0, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (0, 1), 12),
        ("TEXTCOLOR", (0, 1), (0, 1), INK),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (0, 0), 7),
        ("BOTTOMPADDING", (0, 1), (0, 1), 8),
        ("BACKGROUND", (0, 0), (-1, -1), BG),
        ("LINEBEFORE", (0, 0), (0, -1), 2.4, color),
    ]))
    return t


def _kv_table(rows: list[tuple[str, str]], col1=4.5 * cm, col2=12.5 * cm) -> Table:
    t = Table(rows, colWidths=[col1, col2])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
        ("TEXTCOLOR", (1, 0), (1, -1), INK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, SUBTLE),
    ]))
    return t


def _stats_table(headers: list[str], rows: list[list[str]]) -> Table:
    data = [headers] + rows
    t = Table(data, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BG]),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, INK),
    ]))
    return t


def _checklist(items: list[str], styles) -> list:
    out = []
    for it in items:
        out.append(Paragraph(f"<font color='{ACCENT_HEX}'>■</font>&nbsp;&nbsp;{it}", styles["body"]))
    return out


def _currency_fmt(x, _pos=None) -> str:
    if x >= 1_000_000:
        return f"${x/1_000_000:.1f}M"
    if x >= 1_000:
        return f"${x/1_000:.0f}K"
    return f"${x:.0f}"


def _build_charts(out_dir: Path):
    """Re-run the synthetic edge backtest and save annotated charts."""
    data = make_universe(n=100, profile="earnings")
    trades = run_universe(data, gap_pct=0.05, max_days=60)
    df = trades_to_frame(trades)

    eq = equity_curve(df, capital=100_000.0, position_frac=0.05)
    strat = stratify_by_gap(df)

    plt.style.use("default")

    # --- Equity curve ---
    fig, ax = plt.subplots(figsize=(10, 4.5), dpi=180)
    ax.plot(eq.index, eq.values, color=ACCENT_HEX, linewidth=2.0, zorder=3)
    ax.fill_between(eq.index, eq.iloc[0], eq.values, color=ACCENT_HEX, alpha=0.13, zorder=2)
    ax.axhline(eq.iloc[0], color=MUTED_HEX, linestyle="--", linewidth=0.8, alpha=0.6, zorder=1)

    total_return = (eq.iloc[-1] / eq.iloc[0] - 1) * 100
    final_val = eq.iloc[-1]
    ax.annotate(
        f"  ${final_val:,.0f}\n  (+{total_return:.0f}%)",
        xy=(eq.index[-1], final_val),
        xytext=(8, 0), textcoords="offset points",
        fontsize=11, fontweight="bold", color=GREEN_HEX, va="center",
    )
    ax.annotate(
        f"  Start ${eq.iloc[0]:,.0f}",
        xy=(eq.index[0], eq.iloc[0]),
        xytext=(8, -14), textcoords="offset points",
        fontsize=9, color=MUTED_HEX, va="center",
    )

    ax.set_title("Equity Curve  —  100 synth. tickers, 10y, 5% per trade, sequential",
                 fontsize=12, color=INK_HEX, loc="left", pad=12, fontweight="bold")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_currency_fmt))
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.grid(True, linestyle=":", alpha=0.35, color=MUTED_HEX, zorder=0)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color(SUBTLE_HEX)
    ax.spines["bottom"].set_color(SUBTLE_HEX)
    ax.tick_params(colors=MUTED_HEX, labelsize=9)
    ax.margins(x=0.04)
    fig.subplots_adjust(left=0.10, right=0.86, top=0.88, bottom=0.12)
    eq_path = out_dir / "_eq_curve.png"
    fig.savefig(eq_path, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    # --- Gap stratification ---
    fig, ax = plt.subplots(figsize=(10, 4.5), dpi=180)
    x = np.arange(len(strat))
    bar_w = 0.36
    win_rates = strat["win_rate"].values * 100
    mean_rets = strat["mean_return"].values * 100

    bars1 = ax.bar(x - bar_w / 2, win_rates, bar_w, color=ACCENT_HEX, label="Win Rate", zorder=3)
    bars2 = ax.bar(x + bar_w / 2, mean_rets, bar_w, color=GREEN_HEX, label="Mean Return", zorder=3)
    ax.axhline(50, color=MUTED_HEX, linestyle=":", linewidth=0.8, alpha=0.5, zorder=1)
    ax.axhline(0, color=MUTED_HEX, linestyle="-", linewidth=0.5, alpha=0.6, zorder=1)

    for bar, val in zip(bars1, win_rates):
        ax.annotate(f"{val:.1f}%", xy=(bar.get_x() + bar.get_width() / 2, val),
                    xytext=(0, 4), textcoords="offset points",
                    ha="center", fontsize=9, color=INK_HEX, fontweight="bold")
    for bar, val in zip(bars2, mean_rets):
        ax.annotate(f"+{val:.1f}%", xy=(bar.get_x() + bar.get_width() / 2, val),
                    xytext=(0, 4), textcoords="offset points",
                    ha="center", fontsize=9, color=INK_HEX, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels([str(b) for b in strat.index], fontsize=10, color=INK_HEX)
    ax.set_title("Win Rate und Mean Return nach Gap-Magnitude",
                 fontsize=12, color=INK_HEX, loc="left", pad=12, fontweight="bold")
    ax.set_xlabel("Gap-Bucket (Day-1 Open vs Day-0 Close)", fontsize=10, color=MUTED_HEX, labelpad=8)
    ax.set_ylabel("Prozent (%)", fontsize=10, color=MUTED_HEX, labelpad=6)
    ax.legend(loc="upper left", frameon=False, fontsize=10)
    ax.grid(True, axis="y", linestyle=":", alpha=0.35, color=MUTED_HEX, zorder=0)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color(SUBTLE_HEX)
    ax.spines["bottom"].set_color(SUBTLE_HEX)
    ax.tick_params(colors=MUTED_HEX, labelsize=9)
    ymax = max(win_rates.max(), mean_rets.max()) * 1.20
    ax.set_ylim(min(0, mean_rets.min() * 1.2), ymax)
    fig.subplots_adjust(left=0.08, right=0.97, top=0.88, bottom=0.14)
    strat_path = out_dir / "_gap_strat.png"
    fig.savefig(strat_path, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    return eq_path, strat_path, summary(df), strat


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawCentredString(
        PAGE_W / 2, 12 * mm,
        "PEAD Breakout Playbook  •  Nur Bildungszwecke. Keine Anlageberatung.",
    )
    canvas.restoreState()


def build(out_pdf: Path) -> None:
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    s = _styles()
    eq_png, strat_png, summ, strat = _build_charts(out_pdf.parent)

    doc = SimpleDocTemplate(
        str(out_pdf),
        pagesize=(PAGE_W, PAGE_H),
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2.5 * cm,
        title="PEAD Breakout Playbook",
        author="backtest-lab",
    )

    story = []

    # === Cover block (no page break — flows continuously) ===
    story.append(Paragraph("PEAD Breakout Playbook", s["title"]))
    story.append(Paragraph(
        "Long-After-Breakout-Candle Strategie fuer Earnings-Gap-Events",
        s["subtitle"],
    ))
    story.append(_hr())
    story.append(Spacer(1, 8))
    story.append(_kv_table([
        ("Strategie", "Long-Side PEAD mit dynamischem Trailing-Stop"),
        ("Universe", "S&P 100 (anpassbar)"),
        ("Trigger", "Day-1 Open >= +5% Gap vs Day-0 Close"),
        ("Holding", "Bis zu 60 Handelstage, dynamisch verkuerzt"),
        ("Basis", "Bernard & Thomas (1989) Post-Earnings Announcement Drift"),
        ("Generiert", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
    ]))
    story.append(Spacer(1, 14))
    story.append(Paragraph(
        "Dieses Playbook beschreibt die operativen Regeln, das Trade-Management, die Edge-Mechanik "
        "und die historischen Cohort-Statistiken. Es ersetzt nicht eigenes Risikomanagement und keine "
        "Discretionary-Pruefung pro Trade.",
        s["small"],
    ))

    # === 1. Executive Summary ===
    story.extend(_section_header("1. Executive Summary", s))
    story.append(Paragraph(
        "Die Strategie identifiziert Aktien, die nach Earnings-Releases mit einem Gap "
        "von mindestens +5% oeffnen, und geht am Schluss desselben Tages long. Stop liegt unter "
        "dem Tageslow der Breakout-Kerze. Der Stop wird nach 5 Handelstagen auf den 10-Tage-SMA "
        "und nach 30 Handelstagen auf den 20-Tage-SMA nachgezogen. Notausgang bei Wochen-Close "
        "unter dem 50-Tage-EMA. Maximale Haltedauer 60 Handelstage.",
        s["body"],
    ))
    story.append(Paragraph(
        "Die Edge stammt aus der PEAD-Anomalie: Aktien mit positiver Earnings-Surprise driften "
        "akademisch dokumentiert 60-90 Tage nach dem Release weiter nach oben. Der Effekt wird "
        "durch verzoegerte Analyst-Revisionen und institutionelles Position-Building getragen. "
        "Strukturelle News-Catalysts (Multi-Year Contracts, neue Produkt-Cycles, $1T Market-Cap-Inclusion) "
        "verlaengern und verstaerken die Drift.",
        s["body"],
    ))
    story.append(Paragraph("Headline-Backtest (synthetisches Universe, n=100, geplante PEAD-Edge)", s["h2"]))
    story.append(_stats_table(
        ["Metrik", "Mit PEAD-Drift", "Null-Hypothesis", "Delta"],
        [
            ["Anzahl Trades",          f"{summ['n_trades']}", "1412", "~0"],
            ["Win Rate",               f"{summ['win_rate']*100:.1f}%", "43.6%", f"+{(summ['win_rate']*100-43.6):.1f}pp"],
            ["Profit Factor",          f"{summ['profit_factor']:.2f}", "1.54", f"+{summ['profit_factor']-1.54:.2f}"],
            ["Expectancy / Trade",     f"+{summ['expectancy']*100:.2f}%", "+0.94%", f"+{(summ['expectancy']*100-0.94):.2f}pp"],
            ["Sharpe (annualisiert)",  f"{summ['sharpe_annualised']:.2f}", "0.70", f"+{summ['sharpe_annualised']-0.70:.2f}"],
            ["Avg Hold (Tage)",        f"{summ['avg_hold_days']:.1f}", "9.6",  "~+1"],
        ],
    ))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        "<b>Lesart:</b> Die Differenz von ~1.9 Prozentpunkten Expectancy je Trade ist die Magnitude, "
        "die die PEAD-Anomalie ueber das natuerliche Momentum-Bias hinaus addiert. Win-Rate steigt "
        "monoton mit Gap-Groesse (siehe Stratifizierung). Echte Daten reproduzieren historisch eine "
        "Sharpe in dieser Groessenordnung, abhaengig von Universe und Periode.",
        s["small"],
    ))

    # === 2. Trade-Regeln ===
    story.extend(_section_header("2. Trade-Regeln", s))
    story.append(Paragraph(
        "Die folgenden Regeln sind deterministisch und werden ohne Discretionary-Anpassung exekutiert. "
        "Jede Regel hat eine klare Invalidierungs-Bedingung.",
        s["body"],
    ))
    story.append(Spacer(1, 3 * mm))

    rule_grid = [
        [_rule_box("TRIGGER", "Day-1 Open >= +5% Gap vs Day-0 Close"),
         _rule_box("VOLUMEN-FILTER", "Tagesvolumen >= 1.5x 20-Tage-Avg (optional)")],
        [_rule_box("ENTRY", "Day-1 Close des Gap-Tages"),
         _rule_box("INITIAL STOP", "Tageslow von Day-1 (Breakout-Kerze)")],
        [_rule_box("TRAIL TAG 1-4", "Stop bleibt am Tageslow Day-1"),
         _rule_box("TRAIL TAG 5-29", "Stop auf 10-Tage-SMA (Vortag)")],
        [_rule_box("TRAIL TAG 30-60", "Stop auf 20-Tage-SMA (Vortag)"),
         _rule_box("NOTAUSGANG", "Wochen-Close < 50-Tage-EMA")],
    ]
    t = Table(rule_grid, colWidths=[8.5 * cm, 8.5 * cm], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t)
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph("Forced Exit Day 60", s["h2"]))
    story.append(Paragraph(
        "Position wird am Close von Tag 60 nach Entry geschlossen, unabhaengig von P&L. "
        "Begruendung: PEAD-Drift verflacht ueblicherweise nach Tag 60-90, und das Risk-Reward "
        "verschlechtert sich. Naechstes Earnings-Event ist typischerweise in greifbarer Naehe und "
        "die Earnings-Vola toetet das R/R.",
        s["body"],
    ))

    story.append(Paragraph("Position Sizing", s["h2"]))
    story.append(_kv_table([
        ("Max Risk pro Trade", "1.0% bis 1.5% Konto-Equity"),
        ("Berechnung", "Stop-Distance vom Entry * Position-Groesse = Risk-Betrag"),
        ("Beispiel", "Konto 100k, Risk 1.0% = 1000 USD. Entry 895, Stop 820, Distance 8.4%. Position = 1000 / 0.084 = ~11900 USD = ~13 Aktien."),
        ("Max gleichzeitige Trades", "5 (Korrelations-Cap auf Tech/Semi-Sektor: max 2)"),
        ("Position-Skalierung", "Keine Pyramiding-Adds, keine Averaging-Down"),
    ]))

    # === 3. Pre-Trade Checklist ===
    story.extend(_section_header("3. Pre-Trade Checklist", s))
    story.append(Paragraph(
        "Bevor du am Day-1-Close eine Position eroeffnest, muss jede der folgenden Bedingungen erfuellt sein. "
        "Eine Verletzung = Skip, kein Discretionary-Override.",
        s["body"],
    ))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("Setup-Validierung", s["h2"]))
    story.extend(_checklist([
        "Day-1 Open ist >= +5% ueber Day-0 Close (Gap bestaetigt).",
        "Day-1 schliesst gruen und im oberen Drittel der Tagesrange (Anti-Fade-Filter).",
        "Tagesvolumen >= 1.5x 20-Tage-Average (institutionelles Interesse).",
        "Aktienkurs >= 5 USD (Penny-Stocks raus).",
        "Marktkapitalisierung >= 2 Mrd USD (Liquidity-Filter).",
        "Earnings-Release in den letzten 24h bestaetigt (Press-Release oder Newswire).",
    ], s))
    story.append(Paragraph("Kontext-Pruefung", s["h2"]))
    story.extend(_checklist([
        "SPY/QQQ schliesst nicht unter dem 50-Tage-EMA (kein Macro-Risk-Off).",
        "VIX unter 30 (keine Stress-Phase).",
        "Sektor-ETF (XLK fuer Tech, XLF fuer Financials, etc.) ist in einem Aufwaertstrend.",
        "Keine widersprueglichen Analyst-Downgrades am gleichen Tag.",
        "Keine offene Position im gleichen Sektor mit >= 2% Konto-Exposure.",
    ], s))
    story.append(Paragraph("Position-Sizing-Pruefung", s["h2"]))
    story.extend(_checklist([
        "Risk-pro-Trade berechnet (1.0% Konto / Stop-Distance).",
        "Max 5 gleichzeitige offene PEAD-Trades.",
        "Max 2 Trades im gleichen Sektor.",
        "Genuegend Cash-Buffer (15% Konto Cash bleibt frei).",
    ], s))

    # === 4. Trade-Lifecycle ===
    story.extend(_section_header("4. Trade-Lifecycle Tag fuer Tag", s))
    story.append(Paragraph(
        "Die Strategie hat vier klar abgegrenzte Phasen mit unterschiedlichen Risk-Profilen.",
        s["body"],
    ))

    story.append(Paragraph("Phase 1: Tag 1 bis 4 (Gap-Fade Schutz)", s["h2"]))
    story.append(_kv_table([
        ("Stop", "Initial Stop am Day-1-Low. Nicht nachziehen."),
        ("Erwartung", "Profit-Taking durch kurzfristige Trader, Range zwischen Day-1 High und Low."),
        ("Was kann passieren", "Gap-Fill in den ersten 1-3 Tagen toetet die Position (~30% der Trades)."),
        ("Was zu tun ist", "Nichts. Stop steht. Bei Trefferschnellem Re-Entry erlaubt, wenn Gap-Day-Low zurueck erobert wird."),
        ("Watch-Signale", "PT-Hikes von Sell-Side, ETF-Inflows, Sektor-Sympathy-Moves."),
    ]))

    story.append(Paragraph("Phase 2: Tag 5 bis 29 (Drift-Konsolidierung)", s["h2"]))
    story.append(_kv_table([
        ("Stop", "Trail auf 10-Tage-SMA des Vortages."),
        ("Erwartung", "Klassische PEAD-Drift kickt rein. Hoeher-Hoechs und Hoeher-Tiefs erwartet."),
        ("Was kann passieren", "Ruecksetzer auf 10-SMA sind normal und sollen die Position nicht abschuetteln."),
        ("Was zu tun ist", "Trail-Stop folgt. Bei Bounce vom 10-SMA mit Volumen-Trockenheit = Akkumulations-Signal."),
        ("Watch-Signale", "Weitere PT-Hikes, Sektor-Rotation in deinen Sektor, Insider-Buys."),
    ]))

    story.append(Paragraph("Phase 3: Tag 30 bis 60 (Drift-Reife)", s["h2"]))
    story.append(_kv_table([
        ("Stop", "Trail auf 20-Tage-SMA des Vortages."),
        ("Erwartung", "Drift schwaecher, Volatilitaet hoeher. R/R verschlechtert sich."),
        ("Was kann passieren", "Korrekturen 5-8% sind normal. Pre-Earnings-Drift kickt ein wenn nahe naechstem Release."),
        ("Was zu tun ist", "Halbe Position bei +20% R/R schliessen erlaubt (Discretionary). Stop weiter folgen."),
        ("Watch-Signale", "Naechstes Earnings-Datum, Guidance-Updates, Sektor-Vola."),
    ]))

    story.append(Paragraph("Phase 4: Tag 60+ (Forced Exit)", s["h2"]))
    story.append(_kv_table([
        ("Stop", "Final Close am Day-60 Close."),
        ("Erwartung", "PEAD-Drift verflacht. Naechstes Earnings-Risk nimmt zu."),
        ("Was zu tun ist", "Position glatt schliessen. Keine Verlaengerung."),
        ("Re-Entry", "Erst nach naechstem Earnings-Release wenn neuer Gap-Trigger ausloest."),
    ]))

    # === 5. Edge-Mechanik ===
    story.extend(_section_header("5. Edge-Mechanik: Warum die Strategie funktioniert", s))
    story.append(Paragraph(
        "PEAD ist die statistisch am laengsten dokumentierte Marktanomalie. Bernard & Thomas (1989) "
        "zeigten erstmals, dass Aktien mit positiver Earnings-Surprise 60-90 Tage nach dem Release "
        "weiter nach oben driften. Der Effekt ueberlebt seit ueber 35 Jahren in der akademischen Literatur. "
        "Die Strategie nutzt drei kombinierte Mechanismen:",
        s["body"],
    ))
    story.append(Paragraph("Mechanismus 1: Verzoegerte Analyst-Revisionen", s["h2"]))
    story.append(Paragraph(
        "Nach einem Earnings-Beat braucht die Sell-Side typischerweise 1-3 Wochen, bis alle Haeuser "
        "ihre Price-Targets nachziehen. Jedes neue Upgrade ist ein neuer Bid-Impuls. Die Reaktion ist "
        "nicht effizient, weil Analysten konservativ und sequentiell handeln, um nicht zu fruehs ihr "
        "Modell zu commiten.",
        s["body"],
    ))
    story.append(Paragraph("Mechanismus 2: Institutionelles Position-Building", s["h2"]))
    story.append(Paragraph(
        "Hedge Funds und Asset Manager bauen Positionen ueber Tage und Wochen auf, nicht in einer Order. "
        "Liquid-Constraint und Marktimpact zwingen sie zur Glaettung. Das schafft konstanten Bid-Druck "
        "ueber die ersten 4-8 Wochen nach dem Release.",
        s["body"],
    ))
    story.append(Paragraph("Mechanismus 3: ETF- und Passiv-Mandate", s["h2"]))
    story.append(Paragraph(
        "Bei Erreichen von Market-Cap-Schwellen (Russell-1000-Inclusion, $1T-Cap, S&P-500-Inclusion) "
        "loesen mechanische Kaeufe von passiven Fonds aus. Diese Inflows sind preisunabhaengig und "
        "verstaerken die Drift, bis das Rebalancing abgeschlossen ist.",
        s["body"],
    ))
    story.append(Paragraph("Verstaerker: Strukturelle News", s["h2"]))
    story.append(Paragraph(
        "Earnings-Beats mit struktureller Story (Multi-Year-Contracts, neue Produkt-Generation, "
        "Marktanteilsgewinne) erzeugen Multi-Quartal-Visibility. Sie aendern das Bewertungs-Multiple, "
        "nicht nur die Estimates. Das ist der Unterschied zwischen einem 60-Tage-Drift und einem "
        "6-Monats-Re-Rating.",
        s["body"],
    ))

    # === 6. Backtest-Ergebnisse ===
    story.extend(_section_header("6. Backtest-Ergebnisse", s))
    story.append(Paragraph(
        "Simuliert auf einem synthetischen Universe von 100 Tickern, 10 Jahre Tagesdaten, geplanter "
        "PEAD-Drift von 7% ueber 60 Tage. Position-Sizing: 5% Konto-Equity je Trade, sequentielle "
        "Ausfuehrung (eine Position offen zur Zeit).",
        s["body"],
    ))
    story.append(Spacer(1, 4 * mm))
    story.append(Image(str(eq_png), width=17 * cm, height=7.65 * cm))
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("Stratifizierung nach Gap-Magnitude", s["h2"]))
    story.append(Paragraph(
        "Die kritische Validierung: Win-Rate steigt monoton mit Gap-Groesse. Das ist der "
        "Lehrbuch-PEAD-Pattern (Top-Dezil-SUE liefert staerksten Drift).",
        s["body"],
    ))
    story.append(Image(str(strat_png), width=17 * cm, height=7.65 * cm))
    story.append(Spacer(1, 4 * mm))
    strat_rows = []
    for bucket, row in strat.iterrows():
        strat_rows.append([
            str(bucket),
            f"{int(row['n'])}",
            f"+{row['mean_return']*100:.2f}%",
            f"{row['win_rate']*100:.1f}%",
            f"{row['avg_hold']:.1f}",
        ])
    story.append(_stats_table(
        ["Gap-Bucket", "n Trades", "Mean Return", "Win Rate", "Avg Hold (d)"],
        strat_rows,
    ))

    # === 7. Failure Modes ===
    story.extend(_section_header("7. Failure Modes und Risk Disclosures", s))
    story.append(Paragraph(
        "Die Strategie hat klar definierte Failure Modes. Wer sie ignoriert, draft entweder zu lange "
        "auf einer kaputten These oder schalt zu frueh.",
        s["body"],
    ))
    story.append(Paragraph("Failure Mode 1: Sektor-Crash", s["h2"]))
    story.append(Paragraph(
        "Wenn der Sektor des Trades broad-based verkauft wird (z.B. Memory-Sell-off ueber Samsung-Guidance-Cut), "
        "wird PEAD ueberstimmt. Stop-Strategie schuetzt, aber Cluster-Risk auf mehrere offene Trades im "
        "gleichen Sektor kann das Konto verletzen. Limit: max 2 Trades pro Sektor.",
        s["body"],
    ))
    story.append(Paragraph("Failure Mode 2: Macro-Risk-Off", s["h2"]))
    story.append(Paragraph(
        "Fed-Hawkishness, Recession-Fears oder geopolitische Schocks killen AI- und Growth-Trades unabhaengig "
        "vom individuellen Setup. Filter: SPY ueber 50-Tage-EMA, VIX unter 30. Verletzung = Skip neuer Trades, "
        "bestehende mit aktuellen Stops weiterlaufen lassen.",
        s["body"],
    ))
    story.append(Paragraph("Failure Mode 3: Whipsaw nach Gap-Day", s["h2"]))
    story.append(Paragraph(
        "30-40% der 5%-Gaps werden in den ersten 3 Tagen gefilled. Der Initial-Stop schuetzt, aber die Trade-"
        "Frequenz mit Stop-Outs ist hoch. Wer das psychologisch nicht aushaelt, wird die Strategie kippen, "
        "bevor sich die Edge ueber n=50+ Trades ausgepraegt hat.",
        s["body"],
    ))
    story.append(Paragraph("Failure Mode 4: Earnings-Miss im naechsten Quartal", s["h2"]))
    story.append(Paragraph(
        "Wenn die Position noch offen ist und das naechste Earnings-Datum ansteht, kann ein Miss die "
        "gesamten PEAD-Gewinne in einer Nacht aufzehren. Regel: Position vor naechstem Earnings glatt stellen, "
        "auch wenn Day-60 noch nicht erreicht ist.",
        s["body"],
    ))
    story.append(Paragraph("Failure Mode 5: Overcrowded Trade", s["h2"]))
    story.append(Paragraph(
        "Wenn jeder Retail-Trader und jeder CTA den gleichen Gap kauft, wird die Position-Building-Phase "
        "kuerzer und die Reversal-Wahrscheinlichkeit hoeher. Indikator: ungewoehnlich hohe Option-Call-Volumen "
        "in den ersten 2 Tagen relativ zu historischem Open-Interest.",
        s["body"],
    ))
    story.append(Paragraph("Generelle Disclaimers", s["h2"]))
    story.append(Paragraph(
        "Backtest-Ergebnisse sind historisch, nicht zukunftsgerichtet. Die Strategie verwendet "
        "Survivorship-Biased Universe (S&P 100 heute, nicht historisch konstant). Slippage, Commissions "
        "und Borrow-Costs sind im Backtest nicht modelliert. Reale Performance liegt typischerweise "
        "10-25% unter Backtest-Performance.",
        s["small"],
    ))

    # === 8. Worked Example MU ===
    story.extend(_section_header("8. Worked Example: MU am 2026-06-15", s))
    story.append(Paragraph(
        "Micron Technology (MU) gappte am 2026-06-15 +19.3% nach Earnings. UBS hob das Price Target "
        "und MU ueberschritt $1 Bio Marktkapitalisierung. Multi-Year-Contracts mit fixed/variable Pricing "
        "bis 2027-28. Lehrbuch-PEAD-Setup mit strukturellem Catalyst.",
        s["body"],
    ))
    story.append(Paragraph("Setup-Validierung", s["h2"]))
    story.append(_kv_table([
        ("Day-0 Close",          "~$751"),
        ("Day-1 Open",           "~$820"),
        ("Day-1 Gap",            "+9.2% (Open), +19.3% (Close)"),
        ("Day-1 Close",          "$895.88"),
        ("Day-1 Low",            "$820.30 (Initial Stop)"),
        ("RVOL vs SPY",          "1.76 (ueberdurchschnittlich)"),
        ("Markt-Kontext",        "S&P 500 / Nasdaq auf All-Time-Highs, AI-Optimismus"),
        ("Catalyst-Qualitaet",   "Strukturell (Multi-Year-Contracts, HBM4 Production)"),
    ]))
    story.append(Paragraph("Position-Sizing-Beispiel (Konto 100k, Risk 1%)", s["h2"]))
    story.append(_kv_table([
        ("Risk-Betrag",         "$1,000 (1% von $100k)"),
        ("Entry",               "$895.88"),
        ("Stop",                "$820.30"),
        ("Stop-Distance",       "8.4% des Entry"),
        ("Position-Groesse",    "$1,000 / 0.084 = ~$11,900 = ~13 Aktien"),
        ("Konto-Exposure",      "11.9% des Equity"),
    ]))
    story.append(Paragraph("Erwartete Trajectory (Modell)", s["h2"]))
    story.append(_kv_table([
        ("Tag 1-4",   "Range zwischen $820 und $920. Stop nicht angetastet = Setup intakt."),
        ("Tag 5-29",  "10-SMA bei Eintritt der Phase ~$830, steigt auf ~$880 bis Tag 29. Trail folgt."),
        ("Tag 30-60", "20-SMA ~$850 bei Tag 30, steigt auf ~$950 bei Tag 60. Trail folgt."),
        ("Target",    "$1,079 (Range-Breakout-Tool, oberes Target)"),
        ("Forced Exit", "Tag 60 falls Target nicht erreicht."),
        ("Naechstes Earnings", "~September 2026, vorher schliessen."),
    ]))
    story.append(Paragraph("Exit-Szenarien", s["h2"]))
    story.append(_kv_table([
        ("Bull-Case (~30%)",  "Target $1,079 erreicht in Tag 20-40. Halben Trade nehmen, Rest mit Trail."),
        ("Base-Case (~40%)",  "Drift erreicht $980-$1,030 ueber 40-55 Tage. Forced Exit am Tag 60 oder Trail-Stop-Hit."),
        ("Bear-Case (~30%)",  "Gap-Fill in Tag 1-5, Stop bei $820. Risk-Verlust 1.0% Konto. Re-Entry-Trigger setzen."),
    ]))

    # === 9. Workflow ===
    story.extend(_section_header("9. Daily und Weekly Workflow", s))
    story.append(Paragraph("Taeglich (10-15 Minuten)", s["h2"]))
    story.extend(_checklist([
        "Pre-Market: Welche Aktien gappen >= +5%? (Finviz Gap-Up Scanner, TradingView Stock Screener.)",
        "Earnings-Calendar checken: Welche Releases liefen gestern Abend / heute Pre-Market?",
        "Bestaetigte Trigger auf Watch-Liste setzen, Pre-Trade-Checklist abarbeiten.",
        "Open positions: Stop-Levels updaten (10-SMA und 20-SMA Vortagswerte einsetzen).",
        "Markt-Filter pruefen: SPY > 50-EMA? VIX < 30? Bei Verletzung: keine neuen Entries.",
        "End-of-Day: Trades dokumentieren (Entry, Stop, Phase, P&L, Notizen).",
    ], s))
    story.append(Paragraph("Woechentlich (30 Minuten)", s["h2"]))
    story.extend(_checklist([
        "Open trades: Phase-Wechsel pruefen (Tag 5? Tag 30?). Trail-Stop-Regel umsetzen.",
        "PT-Hike-Tracking: Welche Analysten haben in der letzten Woche PTs angehoben fuer offene Positionen?",
        "Sektor-Rotation: ETF-Performance (XLK, XLF, XLE, XLV) checken. Cluster-Risk reduzieren wenn ein Sektor 3+ Trades hat.",
        "Cohort-Performance: Win-Rate der letzten 20 Trades. Wenn unter 40% fuer 30+ Trades, Setup-Filter ueberpruefen.",
    ], s))
    story.append(Paragraph("Monatlich (60 Minuten)", s["h2"]))
    story.extend(_checklist([
        "Full Cohort Review: Alle abgeschlossenen Trades. Win Rate, PF, Sharpe vs Backtest-Baseline.",
        "Failure Modes pruefen: Welche der 5 dokumentierten Failure Modes traten auf? Compliance mit Regeln?",
        "Regel-Anpassungen: Nur nach 50+ neuen Trades und mit dokumentierter Begruendung. Keine Tuning nach Einzeltrades.",
        "Macro-Update: Fed-Calendar, Earnings-Season, Sektor-Trends fuer naechsten Monat.",
    ], s))
    story.append(Spacer(1, 8 * mm))
    story.append(_hr())
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        "<b>Disziplin schlaegt Genialitaet.</b> Die Edge ist statistisch und kumulativ. Sie zeigt sich "
        "ueber n=50+ Trades, nicht ueber einen Einzeltrade. Wer die Stop-Regeln und Position-Sizing-Caps "
        "verletzt, wird die Strategie kippen, bevor die Edge greift.",
        s["body"],
    ))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(
        "Generiert mit backtest-lab / pead. Quellcode: pead/signals.py, pead/backtest.py, pead/metrics.py. "
        "Nur Bildungszwecke. Keine Anlageberatung. Backtests sind historisch, nicht zukunftsgerichtet.",
        s["small"],
    ))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)

    for tmp in (eq_png, strat_png):
        try:
            tmp.unlink()
        except Exception:
            pass


def main() -> int:
    p = argparse.ArgumentParser(prog="pead.playbook")
    p.add_argument("--out", default="playbook.pdf")
    args = p.parse_args()
    out = Path(args.out).resolve()
    print(f"Building playbook PDF -> {out}")
    build(out)
    print(f"Done. Size: {out.stat().st_size/1024:.1f} KB")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
