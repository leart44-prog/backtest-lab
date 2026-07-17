// Generate a print-optimised HTML strategy dossier (German) -> report.html
// Then print to PDF, e.g.:
//   node docs/make_report.js
//   chromium --headless=new --no-sandbox --no-pdf-header-footer \
//     --print-to-pdf=docs/weinstein-strategie.pdf file://$PWD/docs/report.html
const fs = require('fs');
const SCR = __dirname;

// ---------- Diagram A: the 4-stage cycle (computed illustrative curves) ----------
function stageCycleSVG() {
  const W = 820, H = 330, padL = 44, padR = 16, padT = 24, padB = 34;
  const N = 240;
  const price = [], xs = [];
  for (let i = 0; i < N; i++) {
    const t = i / (N - 1); xs.push(t);
    let base;
    if (t < 0.26) base = 30 + Math.sin(t * 40) * 2.2;                 // Stage 1 base
    else if (t < 0.58) base = 30 + (t - 0.26) / 0.32 * 46;           // Stage 2 advance
    else if (t < 0.72) base = 76 + Math.sin((t - 0.58) * 55) * 2.6;  // Stage 3 top
    else base = 76 - (t - 0.72) / 0.28 * 34;                          // Stage 4 decline
    price.push(base + Math.sin(t * 70) * 1.2);
  }
  // trailing SMA (30-period) over the sampled path
  const k = 30, sma = [];
  for (let i = 0; i < N; i++) { let s = 0, c = 0; for (let j = Math.max(0, i - k); j <= i; j++) { s += price[j]; c++; } sma.push(s / c); }
  const pmin = 22, pmax = 82;
  const X = t => padL + t * (W - padL - padR);
  const Y = p => padT + (1 - (p - pmin) / (pmax - pmin)) * (H - padT - padB);
  const path = arr => arr.map((p, i) => (i ? 'L' : 'M') + X(xs[i]).toFixed(1) + ',' + Y(p).toFixed(1)).join(' ');
  const bands = [
    [0, 0.26, '#eef2f7', 'STUFE 1', 'Basis'],
    [0.26, 0.58, '#e6f4ec', 'STUFE 2', 'Aufwärts — KAUFEN'],
    [0.58, 0.72, '#fdf1e0', 'STUFE 3', 'Top'],
    [0.72, 1, '#fbeaea', 'STUFE 4', 'Abwärts — RAUS'],
  ];
  let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Arial,Helvetica,sans-serif">`;
  for (const [a, b, col, lab, sub] of bands) {
    s += `<rect x="${X(a).toFixed(1)}" y="${padT}" width="${(X(b) - X(a)).toFixed(1)}" height="${H - padT - padB}" fill="${col}"/>`;
    const cx = (X(a) + X(b)) / 2;
    s += `<text x="${cx.toFixed(1)}" y="${padT + 14}" text-anchor="middle" font-size="11" font-weight="700" fill="#33445a">${lab}</text>`;
    s += `<text x="${cx.toFixed(1)}" y="${padT + 27}" text-anchor="middle" font-size="9" fill="#66788f">${sub}</text>`;
  }
  s += `<path d="${path(sma)}" fill="none" stroke="#e08a1e" stroke-width="2.4"/>`;
  s += `<path d="${path(price)}" fill="none" stroke="#1a2b4a" stroke-width="1.7"/>`;
  // entry marker at the Stage 1->2 breakout
  const ei = Math.round(0.30 * N);
  s += `<circle cx="${X(xs[ei]).toFixed(1)}" cy="${Y(price[ei]).toFixed(1)}" r="4.5" fill="#159a5a" stroke="#fff" stroke-width="1.5"/>`;
  s += `<text x="${X(xs[ei]).toFixed(1)}" y="${(Y(price[ei]) - 9).toFixed(1)}" text-anchor="middle" font-size="9" font-weight="700" fill="#159a5a">Entry</text>`;
  s += `<text x="${padL}" y="${H - 8}" font-size="9" fill="#8a97a6">Zeit →</text>`;
  s += `</svg>`;
  return s;
}

// ---------- Diagram B: Entry / SL / Trail zoom on a Stage 1->2 breakout ----------
function entryZoomSVG() {
  const W = 820, H = 360, padL = 52, padR = 120, padT = 20, padB = 30;
  const pmin = 90, pmax = 140;
  const X = t => padL + t * (W - padL - padR);
  const Y = p => padT + (1 - (p - pmin) / (pmax - pmin)) * (H - padT - padB);
  // illustrative price path: base ~100 -> breakout -> retest to 100 -> run up
  const pts = [
    [0.00, 98],[0.05, 101],[0.10, 99],[0.14, 100.5],[0.18, 98.5],[0.22, 100],[0.26, 99],[0.30, 100.6],
    [0.34, 103.5],[0.37, 106],   // breakout candle above resistance(100)
    [0.41, 103],[0.45, 100.2],   // retest to the breakout level -> Buy-Limit fills
    [0.50, 104],[0.55, 109.2],   // TP1 zone (2R=109)
    [0.60, 113],[0.66, 118.4],   // TP2 zone (4R=118)
    [0.72, 122],[0.78, 128],[0.85, 133],[0.92, 130],[1.0, 134],
  ];
  const line = pts.map((p, i) => (i ? 'L' : 'M') + X(p[0]).toFixed(1) + ',' + Y(p[1]).toFixed(1)).join(' ');
  const lvl = (p, col, dash, lab, sub) => {
    let o = `<line x1="${padL}" y1="${Y(p).toFixed(1)}" x2="${(W - padR).toFixed(1)}" y2="${Y(p).toFixed(1)}" stroke="${col}" stroke-width="1.4" ${dash ? `stroke-dasharray="${dash}"` : ''}/>`;
    o += `<text x="${(W - padR + 6)}" y="${(Y(p) + 3).toFixed(1)}" font-size="10" font-weight="700" fill="${col}">${lab}</text>`;
    if (sub) o += `<text x="${(W - padR + 6)}" y="${(Y(p) + 15).toFixed(1)}" font-size="8.5" fill="#66788f">${sub}</text>`;
    return o;
  };
  let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Arial,Helvetica,sans-serif">`;
  s += `<rect x="0" y="0" width="${W}" height="${H}" fill="#ffffff"/>`;
  // shaded base region
  s += `<rect x="${padL}" y="${Y(101).toFixed(1)}" width="${(X(0.33) - padL).toFixed(1)}" height="${(Y(98) - Y(101)).toFixed(1)}" fill="#eef2f7"/>`;
  s += `<text x="${((padL + X(0.30)) / 2).toFixed(1)}" y="${(Y(98) + 14).toFixed(1)}" text-anchor="middle" font-size="9" fill="#66788f">Stage-1-Basis</text>`;
  // levels
  s += lvl(136, '#0b7a43', '2 3', 'TP3  8R = 136$', '40 % / Trailing');
  s += lvl(118, '#159a5a', '2 3', 'TP2  4R = 118$', '30 % · dann Trailing an');
  s += lvl(109, '#159a5a', '2 3', 'TP1  2R = 109$', '30 % · dann SL → Break-Even');
  s += lvl(100, '#1a2b4a', '', 'Ausbruch/Entry 100$', 'Buy-Limit-Retest');
  s += lvl(95.5, '#d1403f', '4 3', 'SL  95.50$', 'Entry − 1.5×ATR (R = 4.50$)');
  // price
  s += `<path d="${line}" fill="none" stroke="#1a2b4a" stroke-width="2"/>`;
  // entry dot
  s += `<circle cx="${X(0.45).toFixed(1)}" cy="${Y(100.2).toFixed(1)}" r="5" fill="#159a5a" stroke="#fff" stroke-width="1.6"/>`;
  s += `<text x="${X(0.45).toFixed(1)}" y="${(Y(100.2) + 20).toFixed(1)}" text-anchor="middle" font-size="9" font-weight="700" fill="#159a5a">Buy-Limit Fill</text>`;
  // breakout arrow
  s += `<text x="${X(0.37).toFixed(1)}" y="${(Y(106) - 8).toFixed(1)}" text-anchor="middle" font-size="9" font-weight="700" fill="#e08a1e">Ausbruch ↑ (Vol ≥ 1.5×Ø)</text>`;
  // trailing steps (after TP2)
  const tr = [[0.66,114],[0.72,118],[0.78,124],[0.85,129]];
  let tp = tr.map((p,i)=>(i?'L':'M')+X(p[0]).toFixed(1)+','+Y(p[1]).toFixed(1)).join(' ');
  s += `<path d="${tp}" fill="none" stroke="#d1403f" stroke-width="1.2" stroke-dasharray="2 2"/>`;
  s += `<text x="${X(0.80).toFixed(1)}" y="${(Y(124)-6).toFixed(1)}" font-size="8.5" fill="#d1403f">Trailing-Stop = Hoch − 3×ATR</text>`;
  s += `<text x="${padL}" y="${H - 8}" font-size="9" fill="#8a97a6">Zeit →</text>`;
  s += `</svg>`;
  return s;
}

const A = stageCycleSVG(), B = entryZoomSVG();

// ---------- HTML ----------
const css = `
*{box-sizing:border-box}
:root{--navy:#1a2b4a;--ink:#243244;--mut:#5b6b7d;--line:#dde3ea;--green:#159a5a;--red:#d1403f;--amber:#e08a1e;--bg:#f5f7fa}
html{-webkit-print-color-adjust:exact;print-color-adjust:exact}
body{font-family:Arial,Helvetica,sans-serif;color:var(--ink);font-size:10.5pt;line-height:1.5;margin:0}
h1{font-size:23pt;color:var(--navy);margin:0 0 2px}
h2{font-size:14pt;color:var(--navy);margin:20px 0 8px;padding-bottom:5px;border-bottom:2px solid var(--navy);break-after:avoid}
h3{font-size:11.5pt;color:var(--navy);margin:14px 0 4px;break-after:avoid}
p{margin:6px 0}
.sub{color:var(--mut);font-size:10pt}
.tag{display:inline-block;background:var(--navy);color:#fff;font-size:8pt;font-weight:700;letter-spacing:.5px;padding:2px 8px;border-radius:3px;text-transform:uppercase}
.hero{background:linear-gradient(135deg,#1a2b4a,#2c4470);color:#fff;padding:22px 24px;border-radius:8px;margin:0 0 14px}
.hero h1{color:#fff}
.hero .sub{color:#b9c6d8}
.grid{display:flex;gap:10px;margin:10px 0}
.kpi{flex:1;background:#fff;border:1px solid var(--line);border-radius:6px;padding:10px 12px;text-align:center}
.kpi .v{font-size:17pt;font-weight:800;color:var(--navy)}
.kpi .l{font-size:8.5pt;color:var(--mut);text-transform:uppercase;letter-spacing:.4px}
.box{border:1px solid var(--line);border-radius:6px;padding:12px 14px;margin:10px 0;background:#fff}
.box.green{border-left:4px solid var(--green);background:#f2faf5}
.box.red{border-left:4px solid var(--red);background:#fdf3f3}
.box.amber{border-left:4px solid var(--amber);background:#fdf7ec}
.box.navy{border-left:4px solid var(--navy);background:#f3f6fb}
table{width:100%;border-collapse:collapse;margin:8px 0;font-size:9.5pt}
th,td{border:1px solid var(--line);padding:5px 8px;text-align:left}
th{background:var(--navy);color:#fff;font-weight:700}
tr:nth-child(even) td{background:#f7f9fb}
.mono{font-family:"Courier New",monospace}
.step{display:flex;gap:10px;margin:9px 0;break-inside:avoid}
.step .n{flex:0 0 26px;height:26px;background:var(--navy);color:#fff;border-radius:50%;font-weight:800;font-size:11pt;display:flex;align-items:center;justify-content:center}
.step .b{flex:1}
.step .b b{color:var(--navy)}
.fig{margin:12px 0;border:1px solid var(--line);border-radius:6px;padding:10px;background:#fff;break-inside:avoid}
.figcap{font-size:9pt;color:var(--mut);margin-top:6px;text-align:center}
.pill{display:inline-block;font-size:8.5pt;font-weight:700;padding:1px 7px;border-radius:10px;margin-right:4px}
.pill.g{background:#e6f4ec;color:#0b7a43}.pill.r{background:#fbeaea;color:#b12f2e}.pill.b{background:#eef2f7;color:#33445a}
.pagebreak{break-before:page}
small{color:var(--mut)}
.foot{margin-top:18px;padding-top:8px;border-top:1px solid var(--line);font-size:8.5pt;color:var(--mut);text-align:center}
ul{margin:6px 0 6px 4px;padding-left:18px}li{margin:3px 0}
`;

const html = `<!doctype html><html lang="de"><head><meta charset="utf-8"><title>Weinstein Stage 1→2 Breakout — Strategie-Dossier</title><style>${css}</style></head><body>
<div class="hero">
  <span class="tag">Strategie-Dossier</span>
  <h1>Stan Weinstein · Stage 1→2 Breakout</h1>
  <div class="sub">Long-only Swing-Strategie für Einzelaktien (Daily) · SMA-basiert · maximaler Expected Value<br>
  Optimiert über 498 S&P-500-Aktien (2013–2018) · Stand 17.07.2026</div>
</div>

<div class="grid">
  <div class="kpi"><div class="v">0,89 R</div><div class="l">Expected Value / Trade</div></div>
  <div class="kpi"><div class="v">3,12</div><div class="l">Profit-Faktor</div></div>
  <div class="kpi"><div class="v">57,8 %</div><div class="l">Trefferquote</div></div>
  <div class="kpi"><div class="v">1.454</div><div class="l">Trades / 480 Aktien</div></div>
</div>

<div class="box green"><b>Kernaussage.</b> Von 192 getesteten Konfigurationen liefert der <b>Buy-Limit-Retest eines Stage-1→2-Ausbruchs</b> mit engem 1,5-ATR-Stop, Volumen-Bestätigung und „Gewinner laufen lassen"-Exit den höchsten Erwartungswert: <b>≈ 0,89 R pro Trade</b>. Die Strategie bleibt in <b>beiden</b> Teilperioden (2013–2015 und 2016–2018) klar profitabel — kein Overfit auf eine Marktphase. Buy-Limit schlägt Buy-Stop deutlich (0,89 R vs. 0,32 R).</div>

<h2>1 · Das Konzept — Weinsteins 4 Stufen</h2>
<p>Jede Aktie durchläuft einen Zyklus aus vier Phasen. Die einzige Phase, in der man long kauft, ist der Übergang von <b>Stufe 1 (Basis)</b> zu <b>Stufe 2 (Aufwärtstrend)</b> — der Ausbruch über die Basis, während die 30-Wochen-Linie (150-Tage-SMA) dreht.</p>
<div class="fig">${A}
<div style="text-align:center;font-size:9pt;margin-top:4px"><span style="color:#1a2b4a;font-weight:700">— Kurs</span> &nbsp;&nbsp; <span style="color:#e08a1e;font-weight:700">— 30-Wochen-SMA (150 Tage)</span> &nbsp;&nbsp; <span style="color:#159a5a;font-weight:700">● Entry</span></div>
<div class="figcap">Abb. 1 — Der Weinstein-Zyklus. Gekauft wird ausschließlich der Ausbruch aus der Basis (Stufe 1 → 2), oberhalb der drehenden 150-Tage-SMA.</div></div>

<h2 class="pagebreak">2 · Die Strategie Schritt für Schritt</h2>
<p class="sub">Alle Fenster sind auf Tagesbasis angegeben (30 Wochen = 150 Handelstage). Die App erkennt den Timeframe automatisch.</p>

<div class="step"><div class="n">1</div><div class="b"><b>Trend-Filter (Kontext).</b> Die <b>150-Tage-SMA</b> (Weinstein-Linie) muss <b>flach bis steigend</b> sein — Slope ≥ 0 über die letzten 4 Wochen. Liegt die Linie im Abwärts­trend, wird <u>nicht</u> gekauft. Das hält dich aus Stufe 4 heraus.</div></div>
<div class="step"><div class="n">2</div><div class="b"><b>Stage-1-Basis & Ausbruchsniveau.</b> Das <b>Ausbruchsniveau</b> = höchstes Hoch der letzten <b>4 Wochen (20 Tage)</b> — die Decke der Seitwärts-Basis. Der Ausbruch muss dieses Niveau <b>und</b> die 150-Tage-Linie überschreiten (Stufe-2-Bestätigung).</div></div>
<div class="step"><div class="n">3</div><div class="b"><b>Freshness (frischer Übergang).</b> Der Kurs muss die 150-Tage-Linie <b>erst kürzlich (≤ 12 Wochen)</b> zurückerobert haben. So handelst du echte 1→2-Starts statt spät in einem gereiften Stufe-2-Trend einzusteigen.</div></div>
<div class="step"><div class="n">4</div><div class="b"><b>Volumen-Bestätigung.</b> Am Ausbruchstag muss das Volumen <b>≥ 1,5× seines 10-Wochen-Durchschnitts</b> betragen. Ausbrüche mit Volumen­expansion sind echt — genau wie Weinstein es fordert. (Erhöht den EV von 0,72 R auf 0,89 R.)</div></div>
<div class="step"><div class="n">5</div><div class="b"><b>Entry — Buy-Limit-Retest <span class="pill g">beste Variante</span></b><br>
Nach einem bestätigten Ausbruchs-<i>Schluss</i> über der Basisdecke setzt du eine <b>Buy-Limit-Order genau auf dem Ausbruchsniveau</b>. Du wirst gefüllt, wenn der Kurs zum Retest dorthin zurückfällt (Order ~3 Wochen gültig). Der Retest gibt einen <b>engeren Stop → besseres CRV → höheren EV</b>.<br>
<small>Alternative: <b>Buy-Stop</b> direkt über der Decke (füllt beim Durchbruch). Einfacher, aber niedrigerer EV (0,32 R) — mehr Fehlausbrüche & weiterer Stop.</small></div></div>
<div class="step"><div class="n">6</div><div class="b"><b>Stop-Loss.</b> <span class="pill r">Entry − 1,5 × ATR</span> Der enge Stop definiert dein Risiko <b>R</b>. Ein enger Stop maximiert den EV, weil R klein bleibt und die Gewinner-Vielfachen groß werden.</div></div>
<div class="step"><div class="n">7</div><div class="b"><b>Take-Profit & Trailing — Gewinner laufen lassen.</b> Teilverkäufe in drei Stufen; nach dem ersten Ziel wird das Risiko eliminiert, danach getrailt:
<ul>
<li><b>TP1 bei +2R:</b> 30 % verkaufen → Stop auf <b>Break-Even</b> (Entry).</li>
<li><b>TP2 bei +4R:</b> 30 % verkaufen → <b>Trailing-Stop</b> aktivieren.</li>
<li><b>Rest 40 %:</b> Trailing-Stop = <b>höchstes Hoch − 3 × ATR</b>, Ziel +8R.</li>
</ul></div></div>

<div class="fig">${B}<div class="figcap">Abb. 2 — Ein Trade konkret: Ausbruch über 100 $ (Vol ≥ 1,5×Ø) → Buy-Limit-Retest bei 100 $ → SL 95,50 $ (1,5×ATR, R = 4,50 $) → TP1 109 $ (BE) → TP2 118 $ (Trailing) → Rest läuft.</div></div>

<div class="box navy"><b>Rechenbeispiel.</b> Basisdecke 100 $, ATR = 3 $. Ausbruch schließt über 100 $ auf Volumen. Buy-Limit füllt beim Retest bei <b>100 $</b>. <b>R = 1,5 × 3 = 4,50 $</b>, SL = <b>95,50 $</b>. TP1 = 100 + 2·4,50 = <b>109 $</b> (30 % raus, SL→100). TP2 = <b>118 $</b> (30 % raus, Trailing an). Rest trailt bei Hoch − 9 $ bis TP3 = <b>136 $</b> (8R).</div>

<h2 class="pagebreak">3 · Deep-Dive: Entry — Trigger &amp; wichtige Werte</h2>
<p>Der Entry ist ein <b>zweistufiger Trigger</b>: zuerst wird ein bestätigter Ausbruch <i>erkannt</i> (Order scharf schalten), dann wird auf dem <i>Retest</i> gefüllt. So bekommst du den engen Stop des Retests statt dem weiten Stop eines Verfolgungskaufs.</p>
<div class="box navy" style="background:#0f1b30;color:#dbe4f0"><div class="mono" style="font-size:8.6pt;line-height:1.55;white-space:pre;color:#dbe4f0">TÄGLICH prüfen (kausal — nur abgeschlossene Bars):

A) AUSBRUCH ERKENNEN  → Order scharf schalten
   1. 150-Tage-SMA-Slope ≥ 0            (Trend flach bis steigend)
   2. Freshness: ≤ 60 Tage seit Kurs unter der SMA war
   3. Widerstand = höchstes HOCH der letzten 20 Tage
   4. Ausbruch-Level = Widerstand × 1.001   (0,1 % Puffer)
   5. Tages-SCHLUSS > Ausbruch-Level  UND  Level > 150-SMA
   6. Volumen(heute) ≥ 1.5 × 50-Tage-Durchschnitt
   ⇒ BUY-LIMIT @ Ausbruch-Level, gültig 15 Handelstage

B) FÜLLEN  → Retest der Ausbruchsmarke
   7. Solange Order aktiv: Tages-TIEF ≤ Ausbruch-Level
      UND Tages-Schluss noch > 150-SMA
   ⇒ LONG-FILL @ min(Open, Level)   → sofort SL platzieren</div></div>
<p><b>Welche Werte sind wichtig?</b> Marginaler Effekt jedes Parameters auf den Expected Value (jeweils <i>ein</i> Wert verändert, Rest = Gewinner-Setup, 498 Aktien):</p>
<table>
<tr><th>Stellschraube</th><th>Werte → EV/Trade</th><th>Erkenntnis</th></tr>
<tr><td><b>Order-Typ</b></td><td>Buy-Limit <b>0,89</b> · Buy-Stop 0,34</td><td>⭐ Wichtigster Hebel — Retest &gt;&gt; Verfolgung</td></tr>
<tr><td>Widerstand-Fenster</td><td>10T 0,91 · <b>20T 0,89</b> · 40T 0,87 · 60T 0,88</td><td>Kurze Basis minimal besser, insgesamt robust</td></tr>
<tr><td>Freshness</td><td>aus 0,85 · 30T 0,89 · <b>60T 0,89</b> · 120T 0,88</td><td>Filter hebt Qualität (weniger, bessere Trades)</td></tr>
<tr><td><b>Volumen-Faktor</b></td><td>aus 0,67 · 1,0× 0,76 · <b>1,5× 0,89</b> · 2,0× 0,95</td><td>⭐ Klarer Effekt — höher = mehr EV, weniger Trades</td></tr>
<tr><td>MA-Slope-Minimum</td><td>−2 % 0,86 · <b>0 % 0,89</b> · +0,5 % 0,84 · +1 % 0,82</td><td>„flach genügt" — steilere Vorgabe schadet nur</td></tr>
</table>

<h2 class="pagebreak">4 · Deep-Dive: Stop-Loss</h2>
<div class="box red"><b>Formel:</b> <span class="mono">SL = Entry − 1,5 × ATR(14)</span> &nbsp;→&nbsp; das definiert dein Risiko <b>R = Entry − SL</b>.<br>
Der ATR-Stop <b>passt sich der Volatilität jeder Aktie an</b> — volatile Titel bekommen automatisch mehr Luft, ruhige einen engeren Stop. Ein fester Prozent-Stop kann das nicht.</div>
<h3>Positionsgrößen-Formel (fixes Risiko je Trade)</h3>
<div class="box navy"><span class="mono">Stückzahl = (Risiko-% × Depot) ÷ (Entry − SL)</span><br>
<small>Beispiel: 100.000 € Depot, 1 % Risiko = 1.000 €. Entry 100 $, SL 95,50 $ → R = 4,50 $ → 1.000 € / 4,50 $ ≈ <b>222 Stück</b>. So kostet jeder Verlust-Trade exakt 1 R = 1 % — unabhängig von der Aktie.</small></div>
<p><b>Wie eng stoppen?</b> Enger Stop = kleineres R = jede Bewegung ist mehr R wert → höherer EV:</p>
<table>
<tr><th>Stop-Distanz</th><th>1,0×ATR</th><th>1,25×</th><th>1,5×ATR ✔</th><th>2,0×</th><th>2,5×</th><th>3,0×</th></tr>
<tr><td>EV / Trade</td><td>1,13</td><td>1,01</td><td><b>0,89</b></td><td>0,81</td><td>0,76</td><td>0,75</td></tr>
<tr><td>Trefferquote</td><td>63,7 %</td><td>60,3 %</td><td><b>57,8 %</b></td><td>54,8 %</td><td>54,0 %</td><td>52,8 %</td></tr>
</table>
<div class="box amber"><b>Aber Vorsicht:</b> Sehr enge Stops (1,0×ATR) zeigen im Backtest den höchsten EV, sind live aber <b>anfälliger für Intraday-Rauschen und Slippage</b>. <b>1,5×ATR</b> ist der robuste Kompromiss. Weitere Regeln: <b>Break-Even nach TP1</b> (Stop auf Entry ziehen → Risiko raus); bei Gap unter den Stop wird zum <b>Open</b> ausgeführt (schlechter) — kalkuliere das ein.</div>

<h2 class="pagebreak">5 · Deep-Dive: Target &amp; Trailing</h2>
<h3>Target — Gewinner laufen lassen</h3>
<p>Teilverkäufe in R-Vielfachen. Der Erwartungswert ist <span class="mono">EV = Σ pᵢ · Rᵢ</span> — wenige große Gewinner tragen das Ergebnis, also dürfen die Ziele nicht zu früh greifen:</p>
<table>
<tr><th>Ziel-Leiter</th><th>EV/Trade</th><th>Trefferquote</th><th>Charakter</th></tr>
<tr><td>schnell 1R/2R/3R</td><td>0,62</td><td>76,3 %</td><td>viele kleine Gewinne, niedriger EV</td></tr>
<tr><td>mittel 1,5R/3R/5R</td><td>0,77</td><td>65,8 %</td><td>ausgewogen</td></tr>
<tr><td><b>laufen 2R/4R/8R ✔</b></td><td><b>0,89</b></td><td><b>57,8 %</b></td><td>empfohlen — robust &amp; stark</td></tr>
<tr><td>maximal 3R/6R/12R</td><td>1,09</td><td>46,6 %</td><td>höchster EV, aber &lt; 50 % Treffer</td></tr>
</table>
<p><small>Aufteilung je Stufe: 30 % / 30 % / 40 %. Je größer die Ziele, desto höher der EV — aber die Trefferquote fällt und du gibst mehr zurück. Weinstein-Prinzip: „Verluste kurz, Gewinne lang."</small></p>

<h3>Trailing — so trailt man am besten</h3>
<div class="box green"><b>Methode (Chandelier-Trailing):</b> <span class="mono">Trailing-Stop = höchstes Hoch seit Entry − 3 × ATR</span><br>
Regeln: <b>nur nach oben</b> nachziehen, nie senken · <b>täglich</b> neu berechnen · erst <b>nach TP2 (4R)</b> aktivieren.</div>
<table>
<tr><th>Trailing-Stellschraube</th><th>Werte → EV/Trade</th><th>Erkenntnis</th></tr>
<tr><td>Aktivierung nach…</td><td>TP1 0,86 · <b>TP2 0,89</b> · TP3 0,97</td><td>Später aktivieren = mehr EV (Trend Luft geben)</td></tr>
<tr><td>Trail-Distanz</td><td>1,5×ATR 0,87 · 2× 0,88 · <b>3× 0,89</b> · 4× 0,91</td><td>Weiter trailen = weniger ausgeschüttelt</td></tr>
<tr><td>Break-Even nach…</td><td><b>TP1 0,89 (58 % Treffer)</b> · TP2 0,95 (40 %)</td><td>BE früh = ruhiger; BE spät = mehr EV, mehr Risiko</td></tr>
</table>
<div class="box navy"><b>Best Practice fürs Trailing:</b> <b>spät aktivieren</b> (ab ~4R), <b>weit stellen</b> (3–4×ATR) und <b>nur hochziehen</b>. Zu früh/zu eng zu trailen ist der häufigste Fehler — es würgt genau die großen Stufe-2-Trends ab, von denen der EV lebt.</div>

<h2 class="pagebreak">6 · Zwei Profile — Balanced vs. Maximum-EV</h2>
<p>Da du den maximalen Expected Value willst: dieselbe Logik lässt sich auf höchsten EV trimmen (engerer Stop, höhere Volumen­schwelle, größere Ziele, späteres Trailing). Beide sind in beiden Zeithälften stabil.</p>
<table>
<tr><th>&nbsp;</th><th>Balanced (empfohlen)</th><th>Maximum-EV (aggressiv)</th></tr>
<tr><td>Entry</td><td>Buy-Limit-Retest</td><td>Buy-Limit-Retest</td></tr>
<tr><td>Widerstand-Fenster</td><td>20 Tage</td><td>10 Tage</td></tr>
<tr><td>Volumen-Faktor</td><td>1,5×Ø</td><td>2,0×Ø</td></tr>
<tr><td>Initial-Stop</td><td>1,5×ATR</td><td>1,0×ATR</td></tr>
<tr><td>Ziele</td><td>2R / 4R / 8R</td><td>3R / 6R / 12R</td></tr>
<tr><td>Break-Even / Trailing</td><td>BE n. TP1 · Trail n. TP2 (3×ATR)</td><td>BE n. TP2 · Trail n. TP3 (4×ATR)</td></tr>
<tr><td><b>EV / Trade</b></td><td><b>0,89 R</b></td><td><b>1,71 R</b></td></tr>
<tr><td>Profit-Faktor</td><td>3,12</td><td>4,89</td></tr>
<tr><td>Trefferquote</td><td>57,8 %</td><td>56,0 %</td></tr>
<tr><td>Trades</td><td>1.454</td><td>780</td></tr>
<tr><td>EV H1 2013–15 / H2 2016–18</td><td>0,77 / 1,02</td><td>1,43 / 2,01</td></tr>
</table>
<div class="box amber"><b>Trade-off:</b> Das Max-EV-Profil verdoppelt fast den EV pro Trade, handelt aber <b>~halb so oft</b>, nutzt <b>engere Stops</b> (whipsaw-anfälliger) und <b>größere Ziele</b> (mehr Rückgabe, längere Haltedauer, &lt; 50 % der Trades erreichen die großen Ziele). Für die meisten ist <b>Balanced</b> praktikabler; wer den reinen EV maximieren will und die tieferen Drawdowns aushält, nimmt das aggressive Profil.</div>

<h2 class="pagebreak">7 · Parameter-Referenz (optimale Werte)</h2>
<table>
<tr><th>Parameter</th><th>Optimalwert</th><th>Bedeutung</th></tr>
<tr><td>Weinstein-SMA</td><td class="mono">150 Tage (30 Wo.)</td><td>Trend-Linie; muss flach/steigend sein</td></tr>
<tr><td>Basis-Lookback</td><td class="mono">20 Tage (4 Wo.)</td><td>Höchstes Hoch = Ausbruchsniveau</td></tr>
<tr><td>Freshness</td><td class="mono">≤ 60 Tage (12 Wo.)</td><td>Max. seit Rückeroberung der Linie</td></tr>
<tr><td>Volumen-Faktor</td><td class="mono">≥ 1,5 × Ø</td><td>Bestätigung am Ausbruchstag</td></tr>
<tr><td>Entry-Order</td><td class="mono">Buy-Limit (Retest)</td><td>Alternativ Buy-Stop (niedrigerer EV)</td></tr>
<tr><td>Initial-Stop</td><td class="mono">1,5 × ATR</td><td>Definiert R</td></tr>
<tr><td>Take-Profit</td><td class="mono">2R / 4R / 8R</td><td>30 % / 30 % / 40 %</td></tr>
<tr><td>Break-Even</td><td class="mono">nach TP1</td><td>Stop auf Entry ziehen</td></tr>
<tr><td>Trailing</td><td class="mono">Hoch − 3×ATR (ab TP2)</td><td>Gewinner laufen lassen</td></tr>
<tr><td>Richtung</td><td class="mono">nur Long</td><td>Stufe 4 = raus, nicht shorten</td></tr>
</table>

<h2 class="pagebreak">8 · Ergebnisse & Robustheit</h2>
<table>
<tr><th>Kennzahl</th><th>Gesamt-Universum (498 Aktien) — ehrlich</th><th>Kuratierte 59 Large-Caps (in der App)</th></tr>
<tr><td>Expected Value / Trade</td><td><b>0,89 R</b></td><td>1,48 R</td></tr>
<tr><td>Profit-Faktor</td><td>3,12</td><td>5,71</td></tr>
<tr><td>Trefferquote</td><td>57,8 %</td><td>68,5 %</td></tr>
<tr><td>Trades</td><td>1.454</td><td>178</td></tr>
<tr><td>Aktien positiv</td><td>76 %</td><td>84 %</td></tr>
</table>
<div class="box amber"><b>Zeit-Stabilität (Overfit-Test).</b> Der Erwartungswert bleibt in beiden Hälften stark positiv: <b>H1 2013–2015 = 0,77 R</b>, <b>H2 2016–2018 = 1,02 R</b>. Eine reine Buy-Stop-Variante fällt dagegen auf 0,16 R in H1 — der Buy-Limit-Retest ist der eigentliche Edge.</div>

<h3>Aktien, auf denen es historisch am besten lief</h3>
<p><span class="pill b">AVGO 3,7R</span><span class="pill b">VRSN 3,4R</span><span class="pill b">MAR 3,4R</span><span class="pill b">KLAC 3,3R</span><span class="pill b">HD 3,1R</span><span class="pill b">MCO 2,9R</span><span class="pill b">UNP 2,9R</span><span class="pill b">IT 2,9R</span><span class="pill b">APD 2,6R</span><span class="pill b">GLW 2,6R</span> — klassische Stufe-2-Momentum-Leader.</p>
<div class="box red"><b>Wichtig — richtig lesen.</b> Diese Einzel-EVs beruhen auf nur <b>3–6 Trades</b> je Aktie und sind statistisch dünn. Der Edge liegt in der <b>Breite</b> (funktioniert über 480 Aktien), nicht in einzelnen Titeln. Die richtige Frage ist nicht „welche Aktie", sondern „welches Setup" — und das ist der Stage-1→2-Retest oben.</div>

<h2>9 · Ehrliche Einschränkungen</h2>
<ul>
<li><b>Survivorship Bias:</b> Der Datensatz sind die S&P-500-Mitglieder von 2018 — delistete Verlierer fehlen. Long-only-Ergebnisse sind dadurch <b>optimistisch</b>.</li>
<li><b>Bullenmarkt 2013–2018:</b> günstige Phase für Long-Breakouts; in Bärenmärkten hält der Trend-Filter dich flach, aber die absolute Rendite sinkt.</li>
<li><b>Übertragbarkeit:</b> Die <b>relativen</b> Erkenntnisse (Limit > Stop, enger Stop, Volumen hilft, Gewinner laufen lassen) sind über beide Teilperioden robust; die <b>absoluten</b> Zahlen sind nicht 1:1 in die Zukunft übertragbar.</li>
<li><b>Kosten:</b> ~0,15 % Entry-Slippage modelliert; reale Kommissionen/Spreads je nach Broker.</li>
</ul>

<h2 class="pagebreak">10 · Umsetzung</h2>
<p><b>Im Backtest Lab:</b> Strategie „<b>Stan Weinstein — Stage 1→2 Breakout (Stocks)</b>" wählen → Aktien-Kategorie (59 echte Titel geladen) → „Backtest starten". Optimale Exit-Config ist voreingestellt; Entry standardmäßig Buy-Limit-Retest (auf Buy-Stop umschaltbar).</p>
<p><b>Beim Broker (Order-Mechanik):</b> Nach bestätigtem Ausbruch eine <b>Buy-Limit</b> auf das Ausbruchsniveau legen; parallel eine <b>Stop-Loss-(Sell-Stop)</b>-Order 1,5×ATR darunter. Bei Erreichen von +2R Hälfte/30 % verkaufen und den Stop auf Entry (Break-Even) nachziehen; ab +4R als Trailing-Stop (Hoch − 3×ATR) führen.</p>
<p><b>Frische Daten (ohne Survivorship Bias):</b> <span class="mono">python3 fetch_stocks.py AAPL MSFT NVDA …</span> dort ausführen, wo Yahoo Finance erreichbar ist — die Daten kommen inkl. Volumen im passenden Format, die Strategie läuft direkt darauf.</p>

<div class="foot">Backtest Lab · Weinstein Stage 1→2 Breakout · Branch <span class="mono">claude/stan-weinstein-hidden-markov-qtscb7</span> · Datenquelle: S&amp;P-500 Daily 2013–2018 · Backtest ist keine Anlageberatung.</div>
</body></html>`;

fs.writeFileSync(SCR + '/report.html', html);
console.log('report.html written,', html.length, 'bytes');
