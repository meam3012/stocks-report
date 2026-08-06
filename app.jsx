/* global React, ReactDOM */
const { useState, useEffect, useMemo, useRef } = React;
const D = window.PORTFOLIO_DATA;

// ===== Helpers =====
const fmt = (n, d=2) => n == null ? "—" : n.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
const fmt0 = (n) => n == null ? "—" : Math.round(n).toLocaleString("en-US");
const sign = (n) => n > 0 ? "+" : "";
const cls = (n) => n > 0 ? "up" : n < 0 ? "down" : "flat";

// ===== Topbar =====
function Topbar() {
  const [t, setT] = useState(new Date());
  useEffect(() => {
    const id = setInterval(() => setT(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  const time = t.toLocaleTimeString("en-GB");
  return (
    <div className="topbar">
      <div className="brand">
        <span className="dot"></span>
        <span>PORTFOLIO</span>
        <span className="brand-amber">·TERMINAL</span>
      </div>
      <div className="ticker-strip">
        {D.benchmarks.map(b => (
          <div className="item" key={b.sym}>
            <span className="s">{b.sym}</span>
            <span className="num">{fmt(b.value)}</span>
            <span className={"num " + cls(b.day)}>{sign(b.day)}{fmt(b.day)}%</span>
          </div>
        ))}
      </div>
      <div className="session">
        <span className="live">LIVE</span>
        <span className="dim">{time}</span>
        <span className="amber">{D.asOf}</span>
      </div>
    </div>
  );
}

// ===== KPI panel =====
function KPIs() {
  const t = D.totals;
  return (
    <div className="panel">
      <div className="panel-h"><span className="t">סיכום תיק · PORTFOLIO P&amp;L</span><span className="meta">EOD · MTM</span></div>
      <div className="panel-b tight">
        <div className="kpi-grid">
          <div className="kpi">
            <span className="l">שווי כולל · NAV</span>
            <span className="v num big">₪{fmt0(t.valueILS)}</span>
            <span className={"d num " + cls(t.dayPctILS)}>{sign(t.dayPctILS)}{fmt(t.dayPctILS)}% היום</span>
          </div>
          <div className="kpi">
            <span className="l">רווח/הפסד · UNREALIZED</span>
            <span className={"v num " + cls(t.plILS)}>{sign(t.plILS)}₪{fmt0(t.plILS)}</span>
            <span className={"d num " + cls(t.plPct)}>{sign(t.plPct)}{fmt(t.plPct)}% מהעלות</span>
          </div>
          <div className="kpi">
            <span className="l">מזומן זמין</span>
            <span className="v num">₪{fmt0(D.cash.ils + D.cash.usd * D.fxRate)}</span>
            <span className="d dim num">₪{fmt0(D.cash.ils)} · ${fmt0(D.cash.usd)}</span>
          </div>
          <div className="kpi">
            <span className="l">USD/ILS</span>
            <span className="v num">{fmt(D.fxRate, 4)}</span>
            <span className="d dim num">12 פוזיציות · 2 שווקים</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ===== Benchmarks =====
function Benchmarks() {
  const t = D.totals;
  // approximate portfolio rolling perf from positions weighted
  const port = ["day","week","month"].reduce((acc, k) => {
    let totW = 0, sum = 0;
    D.positions.forEach(p => { totW += p.valueILS; sum += p[k] * p.valueILS; });
    acc[k] = sum / totW; return acc;
  }, {});
  const ytd = t.plPct; // proxy
  return (
    <div className="panel">
      <div className="panel-h"><span className="t">השוואה למדדים · BENCHMARK</span><span className="meta">% TR</span></div>
      <div className="panel-b tight">
        <table className="bench-tbl">
          <thead>
            <tr>
              <th>סמל</th><th className="n">ערך</th>
              <th className="n">יום</th><th className="n">שבוע</th>
              <th className="n">חודש</th><th className="n">YTD</th>
            </tr>
          </thead>
          <tbody>
            <tr className="row-portfolio">
              <td><span className="sym">PORT</span></td>
              <td className="n num">{fmt0(t.valueILS)}</td>
              <td className={"n num " + cls(port.day)}>{sign(port.day)}{fmt(port.day)}%</td>
              <td className={"n num " + cls(port.week)}>{sign(port.week)}{fmt(port.week)}%</td>
              <td className={"n num " + cls(port.month)}>{sign(port.month)}{fmt(port.month)}%</td>
              <td className={"n num " + cls(ytd)}>{sign(ytd)}{fmt(ytd)}%</td>
            </tr>
            {D.benchmarks.map(b => (
              <tr key={b.sym}>
                <td><span className="sym">{b.sym}</span></td>
                <td className="n num">{fmt(b.value)}</td>
                <td className={"n num " + cls(b.day)}>{sign(b.day)}{fmt(b.day)}%</td>
                <td className={"n num " + cls(b.week)}>{sign(b.week)}{fmt(b.week)}%</td>
                <td className={"n num " + cls(b.month)}>{sign(b.month)}{fmt(b.month)}%</td>
                <td className={"n num " + cls(b.ytd)}>{sign(b.ytd)}{fmt(b.ytd)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ===== Performance Chart =====
function PerfChart() {
  const W = 760, H = 260, PAD = { l: 38, r: 14, t: 14, b: 22 };
  const series = [
    { key: "portfolio", color: "#ffb000", label: "PORT", w: 2.4 },
    { key: "snp",       color: "#00ff66", label: "S&P 500", w: 1.4 },
    { key: "ndx",       color: "#00d8ff", label: "NDX", w: 1.4 },
    { key: "ta35",      color: "#ff00aa", label: "TA-35", w: 1.4 },
    { key: "ta125",     color: "#ff5577", label: "TA-125", w: 1.4 },
  ];
  const all = series.flatMap(s => D.perfHistory[s.key]);
  const min = Math.min(...all) - 1, max = Math.max(...all) + 1;
  const days = D.perfHistory.dates.length;
  const x = i => PAD.l + (i / (days - 1)) * (W - PAD.l - PAD.r);
  const y = v => PAD.t + (1 - (v - min) / (max - min)) * (H - PAD.t - PAD.b);
  const path = arr => arr.map((v, i) => (i === 0 ? "M" : "L") + x(i) + " " + y(v)).join(" ");
  const ticks = 4;
  return (
    <div className="panel">
      <div className="panel-h">
        <span className="t">ביצועי תיק VS מדדים · 90D INDEXED</span>
        <span className="meta">100 = T-90</span>
      </div>
      <div className="panel-b">
        <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", direction: "ltr" }}>
          {/* grid */}
          {[...Array(ticks+1)].map((_, i) => {
            const v = min + (max - min) * (i / ticks);
            const yy = y(v);
            return (
              <g key={i}>
                <line x1={PAD.l} x2={W - PAD.r} y1={yy} y2={yy}
                      stroke="#1a2622" strokeWidth="1" strokeDasharray="2 4" />
                <text x={PAD.l - 4} y={yy + 3} textAnchor="end"
                      fill="#6a7a75" fontSize="10" fontFamily="JetBrains Mono">{v.toFixed(0)}</text>
              </g>
            );
          })}
          {/* baseline 100 */}
          <line x1={PAD.l} x2={W - PAD.r} y1={y(100)} y2={y(100)}
                stroke="#4a5550" strokeWidth="1" />
          {/* lines */}
          {series.map(s => (
            <path key={s.key} d={path(D.perfHistory[s.key])}
                  fill="none" stroke={s.color} strokeWidth={s.w}
                  strokeLinejoin="round" strokeLinecap="round"
                  filter={s.key === "portfolio" ? "drop-shadow(0 0 3px rgba(255,176,0,0.6))" : ""} />
          ))}
          {/* legend */}
          <g transform={`translate(${PAD.l}, 6)`}>
            {series.map((s, i) => (
              <g key={s.key} transform={`translate(${i * 96}, 0)`}>
                <line x1="0" x2="14" y1="6" y2="6" stroke={s.color} strokeWidth={s.w} />
                <text x="18" y="9" fill="#e8f0ed" fontSize="10" fontFamily="JetBrains Mono">{s.label}</text>
              </g>
            ))}
          </g>
        </svg>
      </div>
    </div>
  );
}

// ===== Allocation pie =====
function Allocation() {
  const colors = ["#ffb000","#00ff66","#00d8ff","#ff00aa","#ff5577","#a0e030","#ffaa44","#80c0ff","#ff8866","#aaff80","#ff4488","#66ddaa"];
  const sorted = [...D.positions].sort((a,b) => b.valueILS - a.valueILS);
  const total = sorted.reduce((s,p) => s + p.valueILS, 0);
  const cx = 90, cy = 90, R = 76, IR = 44;
  let acc = 0;
  const slices = sorted.map((p, i) => {
    const start = (acc / total) * Math.PI * 2 - Math.PI/2;
    acc += p.valueILS;
    const end = (acc / total) * Math.PI * 2 - Math.PI/2;
    const large = end - start > Math.PI ? 1 : 0;
    const x1 = cx + R * Math.cos(start), y1 = cy + R * Math.sin(start);
    const x2 = cx + R * Math.cos(end),   y2 = cy + R * Math.sin(end);
    const xi1 = cx + IR * Math.cos(start), yi1 = cy + IR * Math.sin(start);
    const xi2 = cx + IR * Math.cos(end),   yi2 = cy + IR * Math.sin(end);
    const d = `M ${x1} ${y1} A ${R} ${R} 0 ${large} 1 ${x2} ${y2} L ${xi2} ${yi2} A ${IR} ${IR} 0 ${large} 0 ${xi1} ${yi1} Z`;
    return { d, color: colors[i % colors.length], p };
  });
  return (
    <div className="panel">
      <div className="panel-h"><span className="t">פילוח תיק · ALLOCATION</span><span className="meta">BY POSITION</span></div>
      <div className="panel-b">
        <div className="alloc-wrap">
          <svg className="alloc-svg" viewBox="0 0 180 180" style={{ direction: "ltr" }}>
            {slices.map((s, i) => (
              <path key={i} d={s.d} fill={s.color} stroke="#050807" strokeWidth="0.8" />
            ))}
            <text x="90" y="86" textAnchor="middle" fill="#e8f0ed"
                  fontSize="9" fontFamily="JetBrains Mono" letterSpacing="2">NAV</text>
            <text x="90" y="100" textAnchor="middle" fill="#ffb000"
                  fontSize="14" fontFamily="JetBrains Mono" fontWeight="700">
              ₪{(D.totals.valueILS/1000).toFixed(0)}K
            </text>
          </svg>
          <div className="alloc-list">
            {slices.map((s, i) => (
              <div className="item" key={i}>
                <span className="swatch" style={{ background: s.color }}></span>
                <span className="sym eng">{s.p.sym}</span>
                <span className="dim">{s.p.market}</span>
                <span className="pct num">{s.p.weight.toFixed(1)}%</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ===== Sparkline =====
function Spark({ data, w = 70, h = 22, color = "#00ff66" }) {
  const min = Math.min(...data), max = Math.max(...data);
  const x = i => (i / (data.length - 1)) * w;
  const y = v => max === min ? h/2 : h - ((v - min) / (max - min)) * h;
  const d = data.map((v, i) => (i === 0 ? "M" : "L") + x(i).toFixed(1) + " " + y(v).toFixed(1)).join(" ");
  return (
    <svg className="spark" width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
      <path d={d} fill="none" stroke={color} strokeWidth="1.4" />
    </svg>
  );
}

// generate fake spark per position
const sparkFor = sym => {
  let seed = sym.split("").reduce((a,c) => a + c.charCodeAt(0), 0);
  const rng = () => { seed = (seed * 9301 + 49297) % 233280; return seed / 233280; };
  const arr = []; let v = 50;
  for (let i = 0; i < 20; i++) { v += (rng() - 0.5) * 8; arr.push(v); }
  return arr;
};

// ===== Positions table =====
function Positions({ onSelect, selected }) {
  return (
    <div className="panel">
      <div className="panel-h">
        <span className="t">פוזיציות · POSITIONS</span>
        <span className="meta">{D.positions.length} HOLDINGS · CLICK FOR DETAIL</span>
      </div>
      <div className="panel-b" style={{ padding: 0, maxHeight: 520 }}>
        <table className="pos-tbl">
          <thead>
            <tr>
              <th>סמל</th>
              <th className="n">מחיר</th>
              <th className="n">יום</th>
              <th className="n">שבוע</th>
              <th className="n">חודש</th>
              <th className="n">שנה</th>
              <th className="n">MA150</th>
              <th className="n">RSI</th>
              <th className="n">P&amp;L</th>
              <th className="n">משקל</th>
              <th>SPARK</th>
              <th>אות</th>
            </tr>
          </thead>
          <tbody>
            {D.positions.map(p => {
              const spark = sparkFor(p.sym);
              const sparkColor = p.month >= 0 ? "#00ff66" : "#ff3344";
              const rsiKind = p.rsi >= 70 ? "over" : p.rsi <= 30 ? "under" : p.rsi >= 60 || p.rsi <= 40 ? "mid" : "";
              const cur = p.market === "US" ? "$" : "₪";
              return (
                <tr key={p.sym} onClick={() => onSelect(p.sym)}
                    style={{ background: selected === p.sym ? "rgba(255,176,0,0.07)" : "" }}>
                  <td>
                    <span className="sym eng">{p.sym}</span>
                    <span className={"market-flag " + p.market.toLowerCase()}>{p.market}</span>
                    <div className="name">{p.name}</div>
                  </td>
                  <td className="n num">{cur}{fmt(p.price)}</td>
                  <td className={"n num " + cls(p.day)}>{sign(p.day)}{fmt(p.day)}%</td>
                  <td className={"n num " + cls(p.week)}>{sign(p.week)}{fmt(p.week)}%</td>
                  <td className={"n num " + cls(p.month)}>{sign(p.month)}{fmt(p.month)}%</td>
                  <td className={"n num " + cls(p.year)}>{sign(p.year)}{fmt(p.year)}%</td>
                  <td className="n">
                    <span className={"ma-pill " + (p.aboveMA ? "above" : "below")}>
                      {sign(p.maDelta)}{fmt(p.maDelta, 1)}%
                    </span>
                  </td>
                  <td className="n">
                    <span className={"rsi-bar " + rsiKind}>
                      <span className="fill" style={{ width: p.rsi + "%" }}></span>
                      <span className="ticks"></span>
                    </span>
                    <span className="rsi-num">{p.rsi}</span>
                  </td>
                  <td className={"n num " + cls(p.pl)}>
                    {sign(p.plPct)}{fmt(p.plPct)}%
                  </td>
                  <td className="n num">{fmt(p.weight, 1)}%</td>
                  <td><Spark data={spark} color={sparkColor} /></td>
                  <td><span className={"tag " + p.verdict}>{p.verdict}</span></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ===== Detail panel — Micha Stock & Pond =====
function StockDetail({ sym }) {
  const p = D.positions.find(x => x.sym === sym) || D.positions[0];
  const cur = p.market === "US" ? "$" : "₪";
  // build an interpretation based on tech / fund signals
  const reasons = [];
  if (p.aboveMA) reasons.push({ t: "✓", c: "up", txt: `מחיר ${fmt(p.price)} מעל MA150 (${fmt(p.ma150)}) — טרנד עולה` });
  else reasons.push({ t: "✗", c: "down", txt: `מתחת ל-MA150 — טרנד יורד, להימנע מקנייה לפי מיכה סטוק` });
  if (p.rsi >= 70) reasons.push({ t: "!", c: "amber", txt: `RSI ${p.rsi} — overbought, סכנת תיקון` });
  else if (p.rsi <= 30) reasons.push({ t: "!", c: "cyan", txt: `RSI ${p.rsi} — oversold, פוטנציאל ריבאונד` });
  else reasons.push({ t: "·", c: "dim", txt: `RSI ${p.rsi} — אזור נייטרלי` });
  if (p.pe) {
    if (p.pe < 20) reasons.push({ t: "✓", c: "up", txt: `P/E ${fmt(p.pe,1)} — סביר/נמוך מבחינה פונדמנטלית` });
    else if (p.pe > 35) reasons.push({ t: "!", c: "amber", txt: `P/E ${fmt(p.pe,1)} — מכפיל גבוה, צמיחה צריכה להצדיק` });
    else reasons.push({ t: "·", c: "dim", txt: `P/E ${fmt(p.pe,1)} — סביר` });
  } else {
    reasons.push({ t: "·", c: "dim", txt: `P/E לא רלוונטי / חברה לא רווחית` });
  }
  reasons.push({ t: "·", c: "dim", txt: `תמיכה ${cur}${fmt(p.support)} · התנגדות ${cur}${fmt(p.resistance)}` });

  return (
    <div className="panel">
      <div className="panel-h">
        <span className="t">ניתוח · {p.sym} · {p.name}</span>
        <span className="meta">MICHA STOCK + FUND · מקבץ</span>
      </div>
      <div className="panel-b">
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 8 }}>
              <div>
                <div className="dim" style={{ fontSize: 10, letterSpacing: ".1em" }}>LAST</div>
                <div className="num" style={{ fontSize: 28, color: "#fff" }}>{cur}{fmt(p.price)}</div>
                <div className={"num " + cls(p.day)} style={{ fontSize: 13 }}>
                  {sign(p.day)}{fmt(p.day)}% היום
                </div>
              </div>
              <span className={"tag " + p.verdict} style={{ fontSize: 14, padding: "6px 14px" }}>{p.verdict}</span>
            </div>
            <table style={{ width: "100%", fontSize: 11, borderCollapse: "collapse" }}>
              <tbody>
                {[
                  ["כמות", `${fmt(p.qty, p.qty < 1 ? 2 : 0)}`],
                  ["מחיר ממוצע", `${cur}${fmt(p.avg)}`],
                  ["שווי שוק", `${cur}${fmt0(p.value)} · ₪${fmt0(p.valueILS)}`],
                  ["רווח/הפסד", `${sign(p.pl)}${cur}${fmt0(p.pl)} (${sign(p.plPct)}${fmt(p.plPct)}%)`, cls(p.pl)],
                  ["נפח יומי", `${p.vol} (avg ${p.avgVol})`],
                  ["MA150", `${cur}${fmt(p.ma150)} · ${sign(p.maDelta)}${fmt(p.maDelta,1)}%`, p.aboveMA ? "up" : "down"],
                  ["P/E", p.pe ? fmt(p.pe, 1) : "—"],
                ].map((r, i) => (
                  <tr key={i}>
                    <td className="dim" style={{ padding: "4px 0", borderBottom: "1px solid #1a2622" }}>{r[0]}</td>
                    <td className={"num " + (r[2] || "")} style={{ padding: "4px 0", borderBottom: "1px solid #1a2622", textAlign: "left", direction: "ltr" }}>{r[1]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div>
            <div className="dim" style={{ fontSize: 10, letterSpacing: ".1em", marginBottom: 6 }}>SIGNALS · אותות</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 6, marginBottom: 12 }}>
              <SignalCell label="טכני" value={p.tech} />
              <SignalCell label="פונדמנטלי" value={p.fund} />
              <SignalCell label="מסקנה" value={p.verdict} primary />
            </div>
            <div className="dim" style={{ fontSize: 10, letterSpacing: ".1em", marginBottom: 6 }}>READOUT · קריאה</div>
            <ul style={{ margin: 0, padding: 0, listStyle: "none", fontFamily: "Heebo", fontSize: 12, lineHeight: 1.7 }}>
              {reasons.map((r, i) => (
                <li key={i} style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: 8, padding: "3px 0" }}>
                  <span className={r.c} style={{ fontFamily: "JetBrains Mono", width: 12 }}>{r.t}</span>
                  <span style={{ color: "#e8f0ed" }}>{r.txt}</span>
                </li>
              ))}
            </ul>
            {p.notes && (
              <div style={{ marginTop: 10, padding: 8, background: "#0f1614", borderRight: "2px solid #ffb000", fontFamily: "Heebo", fontSize: 12, color: "#e8f0ed" }}>
                {p.notes}
              </div>
            )}
            {p.events?.length > 0 && (
              <div style={{ marginTop: 8, fontFamily: "Heebo", fontSize: 11 }}>
                <span className="dim eng" style={{ letterSpacing: ".1em" }}>EVENTS · </span>
                {p.events.map((e, i) => (
                  <span key={i} className="amber" style={{ marginLeft: 8 }}>· {e}</span>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function SignalCell({ label, value, primary }) {
  return (
    <div style={{
      padding: 8, background: "#0f1614",
      border: primary ? "1px solid #ffb000" : "1px solid #233330",
      textAlign: "center",
    }}>
      <div className="dim" style={{ fontSize: 9, letterSpacing: ".1em", marginBottom: 4 }}>{label}</div>
      <span className={"tag " + value}>{value}</span>
    </div>
  );
}

// ===== Trades log =====
function TradesLog() {
  return (
    <div className="panel">
      <div className="panel-h"><span className="t">יומן עסקאות · TRADE LOG</span><span className="meta">L7D</span></div>
      <div className="panel-b" style={{ padding: 0 }}>
        <table className="log-tbl">
          <tbody>
            {D.trades.map((t, i) => (
              <tr key={i}>
                <td className="dim num">{t.date}</td>
                <td><span className="sym eng">{t.sym}</span></td>
                <td><span className={"side-" + t.side}>{t.side}</span></td>
                <td className="num">{fmt(t.qty, t.qty < 1 ? 2 : 0)}</td>
                <td className="num">@{fmt(t.price)}</td>
                <td className="note">{t.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ===== Alerts =====
function Alerts() {
  return (
    <div className="panel">
      <div className="panel-h"><span className="t">התראות · ALERTS</span><span className="meta">{D.alerts.length} ACTIVE</span></div>
      <div className="panel-b" style={{ padding: 0 }}>
        {D.alerts.map((a, i) => (
          <div className={"alert " + a.level} key={i}>
            <span className="flag">{a.flag}</span>
            <span className="sym eng">{a.sym}</span>
            <span className="msg">{a.msg}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ===== AI Daily Summary =====
function AISummary() {
  const t = D.totals;
  const winners = [...D.positions].sort((a,b) => b.day - a.day).slice(0, 2);
  const losers  = [...D.positions].sort((a,b) => a.day - b.day).slice(0, 2);
  const breadth = D.positions.filter(p => p.aboveMA).length;
  return (
    <div className="panel">
      <div className="panel-h">
        <span className="t">סיכום יומי · DAILY BRIEF</span>
        <span className="meta">{D.asOf}</span>
      </div>
      <div className="ai-block">
        <div className="label">תקציר היום</div>
        <p style={{ margin: "4px 0" }}>
          {(() => {
            const dir = v => v > 0 ? "עלה" : v < 0 ? "ירד" : "לא השתנה";
            const sp = D.benchmarks.find(b => b.sym === "S&P 500") || D.benchmarks[0];
            const ndx = D.benchmarks.find(b => b.sym === "NDX") || D.benchmarks[1];
            const ta35 = D.benchmarks.find(b => b.sym === "TA-35") || D.benchmarks[2];
            return <>
              התיק <span className={cls(t.dayPctILS) + " num"}>{sign(t.dayPctILS)}{fmt(t.dayPctILS)}%</span> ביום מסחר {t.dayPctILS >= 0 ? "חיובי" : "שלילי"}.{" "}
              רוחב שוק: <span className="amber num">{breadth}/{D.positions.length}</span> פוזיציות מעל MA150.{" "}
              ה-S&amp;P 500 {dir(sp.day)} ב-{fmt(Math.abs(sp.day))}%,{" "}
              NDX {dir(ndx.day)} ב-{fmt(Math.abs(ndx.day))}%{ta35.day !== 0 ? <>; ת״א-35 {dir(ta35.day)} ב-{fmt(Math.abs(ta35.day))}%</> : ""}.
            </>;
          })()}
        </p>
        <div className="label" style={{ marginTop: 10 }}>הזזות בולטות</div>
        <ul>
          {winners.map(w => (
            <li key={w.sym}>
              <span className="h eng">{w.sym}</span> · <span className="up num">+{fmt(w.day)}%</span> — {w.notes.split(".")[0]}.
            </li>
          ))}
          {losers.map(l => (
            <li key={l.sym}>
              <span className="h eng">{l.sym}</span> · <span className="down num">{fmt(l.day)}%</span> — {l.notes.split(".")[0]}.
            </li>
          ))}
        </ul>
        <div className="stamp">מחושב מ-data.json · אינדיקטורים בלבד · NOT INVESTMENT ADVICE</div>
      </div>
    </div>
  );
}

// ===== Notes =====
function Notes() {
  const [v, setV] = useState(() => localStorage.getItem("portfolio-notes") || D.notes);
  useEffect(() => { localStorage.setItem("portfolio-notes", v); }, [v]);
  return (
    <div className="panel">
      <div className="panel-h"><span className="t">הערות אישיות · MEMO</span><span className="meta">SAVED LOCALLY</span></div>
      <div className="panel-b">
        <textarea className="notes-area" value={v} onChange={e => setV(e.target.value)}
          placeholder="הקלד הערות מעקב, תכנון, דיסציפלינה..."></textarea>
      </div>
    </div>
  );
}

// ===== Status bar =====
function Statusbar() {
  return (
    <div className="statusbar">
      <span>F1 · ניתוח · F2 · התראות · F3 · יומן · / · חיפוש · ESC · ניקוי</span>
      <span><span className="key">P</span> הדפסה</span>
      <span>SESSION · NORMAL</span>
      <span className="amber">TERMINAL v2.6 · {D.asOf}</span>
    </div>
  );
}

// ===== Tweaks panel =====
function Tweaks() {
  const TweakDefaults = /*EDITMODE-BEGIN*/{
    "theme": "green",
    "scanlines": true,
    "compactRows": false
  }/*EDITMODE-END*/;
  const [tw, setTweak] = window.useTweaks(TweakDefaults);

  useEffect(() => {
    document.body.classList.remove("theme-amber", "theme-minimal");
    if (tw.theme === "amber") document.body.classList.add("theme-amber");
    if (tw.theme === "minimal") document.body.classList.add("theme-minimal");
    document.body.style.setProperty("--scanlines-display", tw.scanlines ? "block" : "none");
    if (!tw.scanlines) {
      document.body.style.setProperty("background-image", "none");
      const s = document.getElementById("scan-suppress") || document.createElement("style");
      s.id = "scan-suppress"; s.textContent = "body::before, body::after{display:none!important}";
      document.head.appendChild(s);
    } else {
      const s = document.getElementById("scan-suppress");
      if (s) s.remove();
    }
  }, [tw]);

  const T = window.TweaksPanel, S = window.TweakSection, R = window.TweakRadio, Tg = window.TweakToggle;
  return (
    <T title="Tweaks · עיצוב">
      <S title="ערכת צבעים">
        <R label="THEME" value={tw.theme} onChange={v => setTweak("theme", v)}
           options={[
             { value: "green", label: "Green" },
             { value: "amber", label: "Amber" },
             { value: "minimal", label: "Minimal" },
           ]} />
      </S>
      <S title="אפקטים">
        <Tg label="CRT scanlines" value={tw.scanlines} onChange={v => setTweak("scanlines", v)} />
        <Tg label="שורות צפופות" value={tw.compactRows} onChange={v => setTweak("compactRows", v)} />
      </S>
    </T>
  );
}

// ===== App =====
function App() {
  const [sel, setSel] = useState(D.positions[0].sym);
  return (
    <div>
      <Topbar />
      <div className="shell">
        <div className="row r-summary">
          <KPIs />
          <Benchmarks />
        </div>
        <div className="row r-charts">
          <PerfChart />
          <Allocation />
        </div>
        <div className="row">
          <Positions selected={sel} onSelect={setSel} />
        </div>
        <div className="row r-2">
          <StockDetail sym={sel} />
          <AISummary />
        </div>
        <div className="row r-bottom">
          <TradesLog />
          <Alerts />
          <Notes />
        </div>
      </div>
      <Statusbar />
      <Tweaks />
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
