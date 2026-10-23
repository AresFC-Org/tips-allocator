# TIPS Allocator

Blends STIP, DFIP and LTPZ and shows the look-through real yield, real duration,
average maturity, maturity ladder and buckets, with a solver for a target average
maturity. Live page: https://aresfc-org.github.io/tips-allocator/

## Refresh the data

```bash
python3 fetch_direct.py && python3 build_data.py && python3 make_dashboard.py
git add -A && git commit -m "Refresh holdings" && git push
```

| File | Role |
|---|---|
| `fetch_direct.py` | Downloads STIP, TIP, DFIP and LTPZ holdings into `data/raw/<date>/` (no browser) |
| `fetcher.js` | Older in-browser version of the same downloads, kept as a fallback |
| `build_data.py` | Turns the raw files into `data/tips_data.json` |
| `engine.py` | Reference calculations from the original Google Sheet |
| `dashboard_engine.js` | Same calculations for the page (checked against `engine.py`) |
| `dashboard_template.html` | Page layout |
| `make_dashboard.py` | Builds `docs/index.html` (the site) and `dist/TIPS_ETF_Allocator.html` |

Holdings are public sponsor files (iShares, Dimensional, PIMCO). Expense ratios in
`build_data.py` are prospectus net.
