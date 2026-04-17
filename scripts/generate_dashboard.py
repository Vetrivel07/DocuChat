import argparse
import json
import os
import webbrowser
from pathlib import Path


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def metrics_to_dict(summary: dict) -> dict:
    out = {}
    for m in (summary.get("metrics") or []):
        name = m.get("name", "")
        val = m.get("value")
        count = m.get("count", 0)
        out[name] = {"value": val, "count": count}
    return out


def pct(val):
    if val is None:
        return "N/A"
    return f"{val * 100:.1f}%"


def val_or_na(val):
    if val is None:
        return "null"
    return round(val, 6)


def generate_html(vector_summary: dict, hybrid_summary: dict, comparison: dict) -> str:
    vm = metrics_to_dict(vector_summary)
    hm = metrics_to_dict(hybrid_summary)

    METRICS = [
        ("recall@10",               "Recall@10",               "Source-level retrieval recall"),
        ("citation_precision",      "Citation Precision",      "Cited sources that were correct"),
        ("abstention_accuracy",     "Abstention Accuracy",     "Correctly refused unanswerable queries"),
        ("unsupported_claim_rate",  "Unsupported Claim Rate",  "Answers without grounding (lower=better)"),
        ("answer_correctness_f1",   "Answer F1",               "Token overlap with expected answers"),
        ("multihop_recall@10",      "Multihop Recall@10",      "Multi-hop source retrieval"),
        ("graph_contribution_rate", "Graph Contribution",      "Chunks from graph retrieval (hybrid only)"),
    ]

    def safe_val(m, name):
        return m.get(name, {}).get("value")

    def safe_count(m, name):
        return m.get(name, {}).get("count", 0)

    # Build chart data
    chart_labels = [m[1] for m in METRICS]
    vector_vals = [round((safe_val(vm, m[0]) or 0) * 100, 1) for m in METRICS]
    hybrid_vals = [round((safe_val(hm, m[0]) or 0) * 100, 1) for m in METRICS]

    # Delta data for comparison
    delta_vals = []
    for m in METRICS:
        v = safe_val(vm, m[0])
        h = safe_val(hm, m[0])
        if v is not None and h is not None:
            delta_vals.append(round((h - v) * 100, 1))
        else:
            delta_vals.append(0)

    # Pie data: abstention breakdown
    v_abst = safe_val(vm, "abstention_accuracy") or 0
    h_abst = safe_val(hm, "abstention_accuracy") or 0

    # Matched queries
    v_matched = vector_summary.get("matched_queries", 0)
    h_matched = hybrid_summary.get("matched_queries", 0)
    v_missing = len(vector_summary.get("missing_queries") or [])
    h_missing = len(hybrid_summary.get("missing_queries") or [])

    improved = len(comparison.get("improved_metrics") or [])
    declined = len(comparison.get("declined_metrics") or [])
    unchanged = len(comparison.get("unchanged_metrics") or [])

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>DocuChat — Evaluation Dashboard</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;500;600&display=swap');

  :root {{
    --bg: #0a0e1a;
    --surface: #111827;
    --surface2: #1a2235;
    --border: #1e2d45;
    --accent-v: #3b82f6;
    --accent-h: #10b981;
    --accent-delta: #f59e0b;
    --text: #e2e8f0;
    --text-muted: #64748b;
    --text-dim: #94a3b8;
    --good: #10b981;
    --bad: #ef4444;
    --neutral: #6366f1;
    --radius: 12px;
  }}

  * {{ margin: 0; padding: 0; box-sizing: border-box; }}

  body {{
    font-family: 'DM Sans', sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    padding: 32px 24px;
  }}

  .header {{
    text-align: center;
    margin-bottom: 48px;
  }}

  .header h1 {{
    font-family: 'Space Mono', monospace;
    font-size: 2rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    background: linear-gradient(135deg, var(--accent-v), var(--accent-h));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: 8px;
  }}

  .header p {{
    color: var(--text-muted);
    font-size: 0.9rem;
    font-family: 'Space Mono', monospace;
  }}

  .mode-badges {{
    display: flex;
    justify-content: center;
    gap: 12px;
    margin-top: 16px;
  }}

  .badge {{
    padding: 6px 16px;
    border-radius: 999px;
    font-size: 0.75rem;
    font-family: 'Space Mono', monospace;
    font-weight: 700;
    letter-spacing: 0.05em;
  }}

  .badge-v {{ background: rgba(59,130,246,0.15); color: var(--accent-v); border: 1px solid rgba(59,130,246,0.3); }}
  .badge-h {{ background: rgba(16,185,129,0.15); color: var(--accent-h); border: 1px solid rgba(16,185,129,0.3); }}

  .section-title {{
    font-family: 'Space Mono', monospace;
    font-size: 0.7rem;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 16px;
    padding-left: 4px;
    border-left: 3px solid var(--accent-v);
    padding-left: 10px;
  }}

  /* Summary cards */
  .summary-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 12px;
    margin-bottom: 40px;
  }}

  .sum-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px 16px;
    text-align: center;
  }}

  .sum-card .label {{
    font-size: 0.7rem;
    color: var(--text-muted);
    font-family: 'Space Mono', monospace;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin-bottom: 8px;
  }}

  .sum-card .value {{
    font-size: 1.8rem;
    font-weight: 600;
    font-family: 'Space Mono', monospace;
  }}

  .sum-card .sub {{
    font-size: 0.72rem;
    color: var(--text-muted);
    margin-top: 4px;
  }}

  .c-blue {{ color: var(--accent-v); }}
  .c-green {{ color: var(--accent-h); }}
  .c-amber {{ color: var(--accent-delta); }}
  .c-red {{ color: var(--bad); }}

  /* Metric cards */
  .metrics-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 16px;
    margin-bottom: 40px;
  }}

  .metric-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px;
    position: relative;
    overflow: hidden;
  }}

  .metric-card::before {{
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: linear-gradient(90deg, var(--accent-v), var(--accent-h));
  }}

  .metric-name {{
    font-family: 'Space Mono', monospace;
    font-size: 0.72rem;
    color: var(--text-muted);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-bottom: 4px;
  }}

  .metric-desc {{
    font-size: 0.78rem;
    color: var(--text-dim);
    margin-bottom: 16px;
  }}

  .metric-row {{
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 10px;
  }}

  .metric-mode {{
    font-size: 0.68rem;
    font-family: 'Space Mono', monospace;
    width: 52px;
    color: var(--text-muted);
    flex-shrink: 0;
  }}

  .metric-bar-wrap {{
    flex: 1;
    background: var(--surface2);
    border-radius: 4px;
    height: 8px;
    overflow: hidden;
  }}

  .metric-bar {{
    height: 100%;
    border-radius: 4px;
    transition: width 0.8s ease;
  }}

  .bar-v {{ background: var(--accent-v); }}
  .bar-h {{ background: var(--accent-h); }}

  .metric-val {{
    font-family: 'Space Mono', monospace;
    font-size: 0.82rem;
    font-weight: 700;
    width: 52px;
    text-align: right;
    flex-shrink: 0;
  }}

  .delta-badge {{
    display: inline-block;
    font-family: 'Space Mono', monospace;
    font-size: 0.68rem;
    padding: 2px 8px;
    border-radius: 4px;
    margin-top: 8px;
  }}

  .delta-pos {{ background: rgba(16,185,129,0.15); color: var(--good); }}
  .delta-neg {{ background: rgba(239,68,68,0.15); color: var(--bad); }}
  .delta-neu {{ background: rgba(99,102,241,0.15); color: var(--neutral); }}
  .delta-na  {{ background: rgba(100,116,139,0.1); color: var(--text-muted); }}

  /* Charts */
  .charts-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
    margin-bottom: 40px;
  }}

  .chart-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 24px;
  }}

  .chart-card h3 {{
    font-family: 'Space Mono', monospace;
    font-size: 0.75rem;
    color: var(--text-muted);
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin-bottom: 20px;
  }}

  .chart-wrap {{
    position: relative;
    height: 260px;
  }}

  .chart-wrap-tall {{
    position: relative;
    height: 320px;
  }}

  .full-width {{ grid-column: 1 / -1; }}

  /* Table */
  .comparison-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
  }}

  .comparison-table th {{
    font-family: 'Space Mono', monospace;
    font-size: 0.68rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--text-muted);
    padding: 10px 16px;
    text-align: left;
    border-bottom: 1px solid var(--border);
  }}

  .comparison-table td {{
    padding: 12px 16px;
    border-bottom: 1px solid rgba(30,45,69,0.5);
    color: var(--text-dim);
  }}

  .comparison-table tr:hover td {{
    background: var(--surface2);
  }}

  .trend-improved {{ color: var(--good); font-weight: 600; }}
  .trend-declined {{ color: var(--bad); font-weight: 600; }}
  .trend-unchanged {{ color: var(--neutral); }}
  .trend-na {{ color: var(--text-muted); }}

  @media (max-width: 768px) {{
    .charts-grid {{ grid-template-columns: 1fr; }}
    .full-width {{ grid-column: 1; }}
  }}
</style>
</head>
<body>

<div class="header">
  <h1>DocuChat Evaluation Dashboard</h1>
  <p>Vector vs Hybrid RAG — Comparative Analysis</p>
  <div class="mode-badges">
    <span class="badge badge-v">● VECTOR v2 — {v_matched} queries</span>
    <span class="badge badge-h">● HYBRID v1 — {h_matched} queries</span>
  </div>
</div>

<!-- Summary Cards -->
<p class="section-title">Run Summary</p>
<div class="summary-grid">
  <div class="sum-card">
    <div class="label">Vector Matched</div>
    <div class="value c-blue">{v_matched}</div>
    <div class="sub">{v_missing} missing</div>
  </div>
  <div class="sum-card">
    <div class="label">Hybrid Matched</div>
    <div class="value c-green">{h_matched}</div>
    <div class="sub">{h_missing} missing</div>
  </div>
  <div class="sum-card">
    <div class="label">Improved</div>
    <div class="value c-green">{improved}</div>
    <div class="sub">metrics</div>
  </div>
  <div class="sum-card">
    <div class="label">Declined</div>
    <div class="value c-red">{declined}</div>
    <div class="sub">metrics</div>
  </div>
  <div class="sum-card">
    <div class="label">Unchanged</div>
    <div class="value c-amber">{unchanged}</div>
    <div class="sub">metrics</div>
  </div>
</div>

<!-- Metric Cards -->
<p class="section-title" style="margin-top:8px;">Metric Breakdown — Vector vs Hybrid</p>
<div class="metrics-grid" id="metric-cards">
"""

    for name, label, desc in METRICS:
        vv = safe_val(vm, name)
        hv = safe_val(hm, name)
        vc = safe_count(vm, name)
        hc = safe_count(hm, name)

        vbar = round((vv or 0) * 100, 1)
        hbar = round((hv or 0) * 100, 1)

        v_str = pct(vv) if vv is not None else "N/A"
        h_str = pct(hv) if hv is not None else "N/A"

        if vv is not None and hv is not None:
            delta = (hv - vv) * 100
            # For unsupported_claim_rate lower is better
            if name == "unsupported_claim_rate":
                delta_good = delta < 0
            else:
                delta_good = delta > 0
            delta_cls = "delta-pos" if delta_good else ("delta-neg" if delta != 0 else "delta-neu")
            delta_str = f"{'▲' if delta > 0 else '▼'} {abs(delta):.1f}pp {'improvement' if delta_good else 'decline'}"
        elif hv is not None and vv is None:
            delta_cls = "delta-na"
            delta_str = "hybrid only"
        else:
            delta_cls = "delta-na"
            delta_str = "N/A"

        html += f"""
  <div class="metric-card">
    <div class="metric-name">{label}</div>
    <div class="metric-desc">{desc}</div>
    <div class="metric-row">
      <span class="metric-mode" style="color:var(--accent-v)">VECTOR</span>
      <div class="metric-bar-wrap"><div class="metric-bar bar-v" style="width:{vbar}%"></div></div>
      <span class="metric-val" style="color:var(--accent-v)">{v_str}</span>
    </div>
    <div class="metric-row">
      <span class="metric-mode" style="color:var(--accent-h)">HYBRID</span>
      <div class="metric-bar-wrap"><div class="metric-bar bar-h" style="width:{hbar}%"></div></div>
      <span class="metric-val" style="color:var(--accent-h)">{h_str}</span>
    </div>
    <span class="delta-badge {delta_cls}">{delta_str}</span>
    <div style="font-size:0.68rem;color:var(--text-muted);margin-top:6px;">n={vc} / {hc}</div>
  </div>"""

    html += f"""
</div>

<!-- Charts -->
<p class="section-title">Visual Analysis</p>
<div class="charts-grid">

  <!-- Radar / Grouped Bar -->
  <div class="chart-card full-width">
    <h3>All Metrics — Vector vs Hybrid</h3>
    <div class="chart-wrap-tall">
      <canvas id="barChart"></canvas>
    </div>
  </div>

  <!-- Delta chart -->
  <div class="chart-card">
    <h3>Delta — Hybrid improvement over Vector (pp)</h3>
    <div class="chart-wrap">
      <canvas id="deltaChart"></canvas>
    </div>
  </div>

  <!-- Abstention pie -->
  <div class="chart-card">
    <h3>Abstention Accuracy — Vector vs Hybrid</h3>
    <div class="chart-wrap">
      <canvas id="abstentionChart"></canvas>
    </div>
  </div>

  <!-- Radar chart -->
  <div class="chart-card full-width">
    <h3>Radar — Multi-dimensional Performance</h3>
    <div class="chart-wrap">
      <canvas id="radarChart"></canvas>
    </div>
  </div>

</div>

<!-- Comparison Table -->
<p class="section-title">Detailed Comparison Table</p>
<div style="background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;margin-bottom:40px;">
<table class="comparison-table">
  <thead>
    <tr>
      <th>Metric</th>
      <th>Vector</th>
      <th>Hybrid</th>
      <th>Delta (pp)</th>
      <th>% Change</th>
      <th>Trend</th>
    </tr>
  </thead>
  <tbody>
"""

    for row in (comparison.get("comparison_rows") or []):
        name = row.get("metric", "")
        vv = row.get("vector_value")
        hv = row.get("hybrid_value")
        delta = row.get("delta")
        pct_d = row.get("pct_delta")
        trend = row.get("trend", "n/a")

        v_str = f"{vv*100:.1f}%" if vv is not None else "N/A"
        h_str = f"{hv*100:.1f}%" if hv is not None else "N/A"

        # For unsupported_claim_rate, invert good/bad
        if name == "unsupported_claim_rate":
            trend_cls = "trend-declined" if trend == "improved" else ("trend-improved" if trend == "declined" else f"trend-{trend}")
        else:
            trend_cls = f"trend-{trend}"

        delta_str = f"{delta*100:+.2f}" if delta is not None else "—"
        pct_str = f"{pct_d:+.1f}%" if pct_d is not None else "—"
        trend_label = trend.upper() if trend else "N/A"

        html += f"""    <tr>
      <td style="font-family:'Space Mono',monospace;font-size:0.8rem;color:var(--text)">{name}</td>
      <td style="color:var(--accent-v)">{v_str}</td>
      <td style="color:var(--accent-h)">{h_str}</td>
      <td>{delta_str}</td>
      <td>{pct_str}</td>
      <td class="{trend_cls}">{trend_label}</td>
    </tr>
"""

    html += f"""  </tbody>
</table>
</div>

<script>
const CHART_DEFAULTS = {{
  color: '#94a3b8',
  font: {{ family: 'DM Sans' }},
}};
Chart.defaults.color = CHART_DEFAULTS.color;
Chart.defaults.font.family = CHART_DEFAULTS.font.family;

const LABELS = {json.dumps([m[1] for m in METRICS])};
const V_VALS = {json.dumps(vector_vals)};
const H_VALS = {json.dumps(hybrid_vals)};
const DELTA_VALS = {json.dumps(delta_vals)};

const gridColor = 'rgba(30,45,69,0.8)';
const tickColor = '#64748b';

// Grouped Bar Chart
new Chart(document.getElementById('barChart'), {{
  type: 'bar',
  data: {{
    labels: LABELS,
    datasets: [
      {{
        label: 'Vector',
        data: V_VALS,
        backgroundColor: 'rgba(59,130,246,0.7)',
        borderColor: '#3b82f6',
        borderWidth: 1,
        borderRadius: 4,
      }},
      {{
        label: 'Hybrid',
        data: H_VALS,
        backgroundColor: 'rgba(16,185,129,0.7)',
        borderColor: '#10b981',
        borderWidth: 1,
        borderRadius: 4,
      }}
    ]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{ labels: {{ color: '#94a3b8', font: {{ size: 12 }} }} }},
      tooltip: {{ callbacks: {{ label: ctx => ` ${{ctx.dataset.label}}: ${{ctx.parsed.y}}%` }} }}
    }},
    scales: {{
      x: {{ grid: {{ color: gridColor }}, ticks: {{ color: tickColor }} }},
      y: {{ grid: {{ color: gridColor }}, ticks: {{ color: tickColor, callback: v => v + '%' }}, min: 0, max: 100 }}
    }}
  }}
}});

// Delta Chart
const deltaColors = DELTA_VALS.map((v, i) => {{
  const name = LABELS[i];
  // For unsupported claim rate, negative delta is good
  if (name === 'Unsupported Claim Rate') return v < 0 ? 'rgba(16,185,129,0.8)' : 'rgba(239,68,68,0.8)';
  return v >= 0 ? 'rgba(16,185,129,0.8)' : 'rgba(239,68,68,0.8)';
}});

new Chart(document.getElementById('deltaChart'), {{
  type: 'bar',
  data: {{
    labels: LABELS,
    datasets: [{{
      label: 'Delta (pp)',
      data: DELTA_VALS,
      backgroundColor: deltaColors,
      borderRadius: 4,
    }}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{ callbacks: {{ label: ctx => ` ${{ctx.parsed.y > 0 ? '+' : ''}}${{ctx.parsed.y}}pp` }} }}
    }},
    scales: {{
      x: {{ grid: {{ color: gridColor }}, ticks: {{ color: tickColor, font: {{ size: 10 }} }} }},
      y: {{ grid: {{ color: gridColor }}, ticks: {{ color: tickColor, callback: v => v + 'pp' }} }}
    }}
  }}
}});

// Abstention Pie Chart
new Chart(document.getElementById('abstentionChart'), {{
  type: 'doughnut',
  data: {{
    labels: ['Vector Correct', 'Vector Wrong', 'Hybrid Correct', 'Hybrid Wrong'],
    datasets: [
      {{
        label: 'Vector',
        data: [{round(v_abst*100,1)}, {round((1-v_abst)*100,1)}, 0, 0],
        backgroundColor: ['rgba(59,130,246,0.8)', 'rgba(59,130,246,0.2)', 'transparent', 'transparent'],
        borderWidth: 0,
      }},
      {{
        label: 'Hybrid',
        data: [0, 0, {round(h_abst*100,1)}, {round((1-h_abst)*100,1)}],
        backgroundColor: ['transparent', 'transparent', 'rgba(16,185,129,0.8)', 'rgba(16,185,129,0.2)'],
        borderWidth: 0,
      }}
    ]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{ position: 'bottom', labels: {{ color: '#94a3b8', font: {{ size: 11 }} }} }},
      tooltip: {{ callbacks: {{ label: ctx => ` ${{ctx.label}}: ${{ctx.parsed}}%` }} }}
    }},
    cutout: '55%',
  }}
}});

// Radar Chart
const radarLabels = LABELS.filter((_, i) => V_VALS[i] > 0 || H_VALS[i] > 0);
const radarV = V_VALS.filter((v, i) => V_VALS[i] > 0 || H_VALS[i] > 0);
const radarH = H_VALS.filter((v, i) => V_VALS[i] > 0 || H_VALS[i] > 0);

new Chart(document.getElementById('radarChart'), {{
  type: 'radar',
  data: {{
    labels: radarLabels,
    datasets: [
      {{
        label: 'Vector',
        data: radarV,
        borderColor: '#3b82f6',
        backgroundColor: 'rgba(59,130,246,0.15)',
        pointBackgroundColor: '#3b82f6',
        pointRadius: 4,
        borderWidth: 2,
      }},
      {{
        label: 'Hybrid',
        data: radarH,
        borderColor: '#10b981',
        backgroundColor: 'rgba(16,185,129,0.15)',
        pointBackgroundColor: '#10b981',
        pointRadius: 4,
        borderWidth: 2,
      }}
    ]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{ labels: {{ color: '#94a3b8' }} }}
    }},
    scales: {{
      r: {{
        grid: {{ color: gridColor }},
        pointLabels: {{ color: '#94a3b8', font: {{ size: 11 }} }},
        ticks: {{ color: tickColor, backdropColor: 'transparent', stepSize: 20 }},
        min: 0, max: 100,
      }}
    }}
  }}
}});
</script>

</body>
</html>"""

    return html


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vector-summary", default="storage/eval/runs/vector/summary.json")
    parser.add_argument("--hybrid-summary", default="storage/eval/runs/hybrid/summary.json")
    parser.add_argument("--comparison", default="storage/eval/comparison/vector_vs_hybrid.json")
    parser.add_argument("--output", default="storage/eval/dashboard/eval_dashboard.html")
    parser.add_argument("--open", action="store_true", help="Open in browser after generating")
    args = parser.parse_args()

    vector_summary = load_json(Path(args.vector_summary))
    hybrid_summary = load_json(Path(args.hybrid_summary))
    comparison = load_json(Path(args.comparison))

    if not vector_summary:
        print(f"⚠️  Vector summary not found at {args.vector_summary}")
        print("   Run: python scripts/run_eval.py --retrieval-mode vector_v2 first")

    if not hybrid_summary:
        print(f"⚠️  Hybrid summary not found at {args.hybrid_summary}")
        print("   Run: python scripts/run_eval.py --retrieval-mode hybrid_v1 first")

    html = generate_html(vector_summary, hybrid_summary, comparison)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ Dashboard generated: {output_path}")

    if args.open:
        webbrowser.open(output_path.resolve().as_uri())
    else:
        print(f"   Open in browser: {output_path.resolve()}")


if __name__ == "__main__":
    main()