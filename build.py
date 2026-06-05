#!/usr/bin/env python3
"""
Build a self-contained index.html for GitHub Pages.
Embeds aircraft_data.json and uses Plotly.js + vanilla JS for interactive filtering.

Run:  uv run python build.py
Out:  _site/index.html
"""
import json
import subprocess
import sys
from pathlib import Path

DATA_FILE = Path("aircraft_data.json")
OUT_DIR   = Path("_site")

# Same palette as app.py
PLOTLY_PALETTE = [
    "#636EFA","#EF553B","#00CC96","#AB63FA","#FFA15A",
    "#19D3F3","#FF6692","#B6E880","#FF97FF","#FECB52",
]
DARK24 = [
    "#2E91E5","#E15F99","#1CA71C","#FB0D0D","#DA16FF",
    "#222A2A","#B68100","#750D86","#EB663B","#511CFB",
    "#00A08B","#FB00D1","#FC0080","#B2828D","#6C7C32",
    "#778AAE","#862A16","#A777F1","#620042","#1616A7",
    "#DA60CA","#6C4516","#0D2A63","#AF0038",
]
LIGHT24 = [
    "#FD3216","#00FE35","#6A76FC","#FED4C4","#FE00CE",
    "#0DF9FF","#F6F926","#FF9616","#479B55","#EEA6FB",
    "#DC587D","#D626FF","#6E899C","#00B5F7","#B68E00",
    "#C9FBE5","#FF0092","#22FFA7","#E3EE9E","#86CE00",
    "#BC7196","#7E7DCD","#FC6955","#E48F72",
]
PALETTE = PLOTLY_PALETTE + DARK24 + LIGHT24


def main() -> None:
    if not DATA_FILE.exists():
        print("No data file — running scraper …")
        subprocess.run([sys.executable, "scrape.py"], check=True)

    records = [
        r for r in json.loads(DATA_FILE.read_text())
        if r.get("range_km") and r.get("capacity")
    ]

    OUT_DIR.mkdir(exist_ok=True)
    html = _render(records)
    out = OUT_DIR / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"Built {out}  ({len(records)} aircraft)")


def _render(records: list[dict]) -> str:
    manufacturers = sorted({r["manufacturer"] for r in records})
    color_map = {m: PALETTE[i % len(PALETTE)] for i, m in enumerate(manufacturers)}

    valid_years = [r["first_flight"] for r in records if r.get("first_flight")]
    year_min, year_max = min(valid_years), max(valid_years)

    data_json    = json.dumps(records, ensure_ascii=False)
    palette_json = json.dumps(color_map, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Aircraft Range vs Capacity</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js" charset="utf-8"></script>
  <link  rel="stylesheet" href="https://cdn.jsdelivr.net/npm/tom-select@2.3.1/dist/css/tom-select.min.css">
  <script src="https://cdn.jsdelivr.net/npm/tom-select@2.3.1/dist/js/tom-select.complete.min.js"></script>
  <link  rel="stylesheet" href="https://cdn.jsdelivr.net/npm/nouislider@15.8.1/dist/nouislider.min.css">
  <script src="https://cdn.jsdelivr.net/npm/nouislider@15.8.1/dist/nouislider.min.js"></script>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{
      font-family: 'Segoe UI', Arial, sans-serif;
      margin: 0; padding: 20px 24px;
      max-width: 1500px; margin-inline: auto;
      background: #fff;
    }}
    h1  {{ margin: 0 0 4px; font-size: 1.6rem; }}
    .sub {{ margin: 0 0 18px; color: #666; font-size: .9rem; }}
    .filters {{
      display: flex; gap: 32px; flex-wrap: wrap;
      background: #f5f7fa; border-radius: 10px;
      padding: 14px 20px; margin-bottom: 16px;
      align-items: flex-start;
    }}
    .filter-group {{ flex: 1; min-width: 260px; }}
    .filter-group label {{
      font-weight: 600; font-size: .85rem;
      display: block; margin-bottom: 6px;
    }}
    .year-group {{ flex: 2; min-width: 340px; }}
    #year-slider {{ margin-top: 18px; }}
    .noUi-connect {{ background: #636EFA; }}
    #chart {{ height: 72vh; }}
    #status {{ text-align: center; color: #888; font-size: .85rem; margin-top: 6px; }}
  </style>
</head>
<body>
  <h1>Commercial Aircraft — Range vs. Capacity</h1>
  <p class="sub">
    Source: Wikipedia. Hover a point for details.
    Click legend entries to toggle manufacturers.
    ◆ wide-body (2-class seating) · ● narrow-body (1-class seating)
  </p>

  <div class="filters">
    <div class="filter-group">
      <label for="mfr-select">Manufacturer</label>
      <select id="mfr-select" multiple placeholder="All manufacturers — click to filter …"></select>
    </div>
    <div class="filter-group year-group">
      <label>First Flight Year</label>
      <div id="year-slider"></div>
    </div>
  </div>

  <div id="chart"></div>
  <div id="status"></div>

<script>
const AIRCRAFT = {data_json};
const COLOR_MAP = {palette_json};
const YEAR_MIN = {year_min};
const YEAR_MAX = {year_max};

// ── Layout (must be defined before any event handler fires) ──────────────────
const manufacturers = [...new Set(AIRCRAFT.map(d => d.manufacturer))].sort();
const layout = {{
  xaxis: {{ title: 'Range (km)', tickformat: ',', gridcolor: '#eee', showgrid: true, zeroline: false }},
  yaxis: {{ title: 'Typical passenger capacity', gridcolor: '#eee', showgrid: true, zeroline: false }},
  plot_bgcolor: 'white', paper_bgcolor: 'white',
  hovermode: 'closest',
  legend: {{
    title: {{ text: 'Manufacturer<br><sup>◆ wide-body · ● narrow-body</sup>', font: {{ size: 12 }} }},
    yanchor: 'top', y: 0.99, xanchor: 'left', x: 1.01,
    bgcolor: 'rgba(255,255,255,0.85)', bordercolor: '#ddd', borderwidth: 1,
  }},
  margin: {{ l: 60, r: 200, t: 20, b: 60 }},
}};
Plotly.newPlot('chart', [], layout, {{ responsive: true }});

// ── Manufacturer multi-select (Tom Select) ────────────────────────────────────
const sel = document.getElementById('mfr-select');
manufacturers.forEach(m => {{
  const o = document.createElement('option');
  o.value = o.text = m;
  sel.appendChild(o);
}});
const ts = new TomSelect('#mfr-select', {{
  plugins: ['remove_button'],
  maxOptions: null,
  onInitialize() {{}},
}});
ts.on('change', updateChart);

// ── Year range slider (noUiSlider) ────────────────────────────────────────────
const sliderEl = document.getElementById('year-slider');
noUiSlider.create(sliderEl, {{
  start: [YEAR_MIN, YEAR_MAX],
  step: 1,
  connect: true,
  range: {{ min: YEAR_MIN, max: YEAR_MAX }},
  tooltips: [
    {{ to: v => Math.round(v) }},
    {{ to: v => Math.round(v) }},
  ],
}});
sliderEl.noUiSlider.on('update', updateChart);

// ── Filter + render ───────────────────────────────────────────────────────────
function updateChart() {{
  const selected = ts.getValue();          // [] or array of manufacturer strings
  const [y0, y1] = sliderEl.noUiSlider.get(true).map(Number);

  const filtered = AIRCRAFT.filter(d => {{
    if (selected.length && !selected.includes(d.manufacturer)) return false;
    if (d.first_flight != null && (d.first_flight < y0 || d.first_flight > y1)) return false;
    return true;
  }});

  const traces = [];
  manufacturers.forEach(mfr => {{
    const mfrData = filtered.filter(d => d.manufacturer === mfr);
    if (!mfrData.length) return;

    [['wide', 'diamond', 11], ['narrow', 'circle', 9]].forEach(([body, sym, sz]) => {{
      const sub = mfrData.filter(d => d.body_type === body);
      if (!sub.length) return;
      traces.push({{
        x: sub.map(d => d.range_km),
        y: sub.map(d => d.capacity),
        mode: 'markers+text',
        type: 'scatter',
        name: mfr,
        legendgroup: mfr,
        showlegend: body === 'wide',
        marker: {{
          symbol: sym, size: sz,
          color: COLOR_MAP[mfr], opacity: 0.85,
          line: {{ width: 0.8, color: 'white' }},
        }},
        text: sub.map(d => d.name),
        textposition: 'top center',
        textfont: {{ size: 9, color: COLOR_MAP[mfr] }},
        customdata: sub.map(d => [
          d.manufacturer,
          d.first_flight ?? 'unknown',
          d.body_type,
        ]),
        hovertemplate:
          '<b>%{{text}}</b><br>' +
          'Manufacturer: %{{customdata[0]}}<br>' +
          'Range: %{{x:,}} km<br>' +
          'Capacity: %{{y}} pax<br>' +
          'First flight: %{{customdata[1]}}<br>' +
          'Body: %{{customdata[2]}}' +
          '<extra></extra>',
      }});
    }});
  }});

  Plotly.react('chart', traces, layout);

  const n = filtered.length;
  const nMfr = new Set(filtered.map(d => d.manufacturer)).size;
  document.getElementById('status').textContent =
    `Showing ${{n}} aircraft from ${{nMfr}} manufacturers`;
}}

updateChart();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
