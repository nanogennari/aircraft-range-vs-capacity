# Aircraft Range vs Capacity

An interactive scatter plot of commercial jet airliners comparing range and typical passenger capacity, built from Wikipedia data.

**[Live demo →](https://nanogennari.github.io/aircraft-range-vs-capacity/)**

## Features

- 170+ aircraft variants across all major manufacturers
- Wide-body (◆) and narrow-body (●) distinguished by marker shape
- Wide-body variants use 2-class seating; narrow-body use 1-class (all-economy)
- Filter by manufacturer (multi-select) and first-flight year (range slider)
- Data refreshed weekly from Wikipedia via GitHub Actions

## Stack

| Layer | Tool |
|---|---|
| Data | Wikipedia (scraped with `requests` + `beautifulsoup4`) |
| Local app | Plotly Dash |
| Static site | Plotly.js · Tom Select · noUiSlider |
| CI/CD | GitHub Actions → GitHub Pages |

## Getting started

Requires [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/nanogennari/aircraft-range-vs-capacity.git
cd aircraft-range-vs-capacity
uv sync
```

### Run the interactive app (local)

```bash
uv run python app.py
# open http://127.0.0.1:8050
```

### Scrape fresh data

```bash
uv run python scrape.py          # uses cached aircraft_data.json if it exists
uv run python scrape.py --fresh  # force re-scrape
```

### Build the static site

```bash
uv run python build.py
# output: _site/index.html
```

## Data coverage

Scrapes the [List of jet airliners](https://en.wikipedia.org/wiki/List_of_jet_airliners) Wikipedia article plus supplementary pages for multi-generation families (737 Classic/NG/MAX, 747SP/400/8, A320neo family). Each aircraft page is parsed with three fallback strategies:

1. Variant comparison table (columns = variants, rows = specs)
2. Flat two-column spec table
3. Bullet-list spec section

Freighter-only variants are excluded. Body type is detected from the variant name and page URL.

## License

MIT
