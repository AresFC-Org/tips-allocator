#!/usr/bin/env python3
"""Assemble data/raw/<asOf>/{STIP,TIP,DFIP,LTPZ}.psv into data/tips_data.json.

Usage:  python3 build_data.py [asOf]      (default: newest folder under data/raw)

Output schema (data/tips_data.json):
  asOf            per-feed as-of dates
  generatedAt     ISO timestamp
  universe        one row per TIPS CUSIP: maturity, coupon, price, realDur, realYtm, source
  funds           per ETF: name, expense (decimal), holdings [{cusip, weight}] normalized to 1.0
  checks          coverage / weight-sum diagnostics
The dashboard computes years-to-maturity from today's date at render time, like the
sheet's YEARFRAC(TODAY(), maturity) column, so the JSON carries maturity dates, not tenors.
"""
import json, os, sys, datetime as dt

ROOT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(ROOT, 'data', 'raw')
OUT = os.path.join(ROOT, 'data', 'tips_data.json')

# Expense ratios carried from the Google Sheet (not re-verified against current prospectuses).
FUNDS = {
    'STIP': {'name': 'iShares 0-5 Year TIPS Bond ETF', 'expense': 0.0003},
    'DFIP': {'name': 'Dimensional Inflation-Protected Securities ETF', 'expense': 0.0011},
    'LTPZ': {'name': 'PIMCO 15+ Year US TIPS Index ETF', 'expense': 0.0020},
}

def read_psv(path):
    meta, rows, header = {}, [], None
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\n')
            if not line:
                continue
            if header is None and '=' in line and '|' not in line:
                k, v = line.split('=', 1); meta[k] = v; continue
            if header is None:
                header = line.split('|'); continue
            vals = line.split('|')
            rows.append(dict(zip(header, vals)))
    return meta, rows

def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None

def main():
    dates = sorted(d for d in os.listdir(RAW) if os.path.isdir(os.path.join(RAW, d)))
    asof = sys.argv[1] if len(sys.argv) > 1 else dates[-1]
    d = os.path.join(RAW, asof)
    stip_m, stip = read_psv(os.path.join(d, 'STIP.psv'))
    tip_m, tip = read_psv(os.path.join(d, 'TIP.psv'))
    dfip_m, dfip = read_psv(os.path.join(d, 'DFIP.psv'))
    ltpz_m, ltpz = read_psv(os.path.join(d, 'LTPZ.psv'))

    # Universe: TIP analytics first, STIP fills the sub-1-year bonds TIP excludes.
    universe = {}
    for src, rows in (('TIP', tip), ('STIP', stip)):
        for r in rows:
            if r.get('sector') != 'Treasuries' or not r.get('maturity'):
                continue
            c = r['cusip']
            if c in universe:
                continue
            universe[c] = {
                'cusip': c, 'name': 'TREASURY (CPI) NOTE', 'maturity': r['maturity'],
                'coupon': f(r['coupon']), 'price': f(r['price']),
                'realDur': f(r['realDur']), 'realYtm': f(r['realYtm']), 'source': src,
            }

    def holdings(rows, wkey, bond_filter):
        h = [(r['cusip'], f(r[wkey])) for r in rows if bond_filter(r) and f(r[wkey])]
        tot = sum(w for _, w in h)
        return [{'cusip': c, 'weight': w / tot} for c, w in h], tot

    funds, checks = {}, {}
    stip_h, stip_tot = holdings(stip, 'weight', lambda r: r.get('sector') == 'Treasuries' and r.get('maturity'))
    dfip_h, dfip_tot = holdings(dfip, 'weight', lambda r: r.get('cusip') and r.get('maturity'))
    ltpz_h, ltpz_tot = holdings(ltpz, 'pct', lambda r: r.get('type') == 'GOVERNMENT' and r.get('cusip', '').startswith('9128') and f(r['pct']) and f(r['pct']) > 0.05)
    for tk, h, tot, unit in (('STIP', stip_h, stip_tot, 100), ('DFIP', dfip_h, dfip_tot, 1), ('LTPZ', ltpz_h, ltpz_tot, 100)):
        missing = [x['cusip'] for x in h if x['cusip'] not in universe]
        funds[tk] = dict(FUNDS[tk], holdings=h)
        checks[tk] = {'nHoldings': len(h), 'bondWeightBeforeNormalize': round(tot / unit, 5), 'missingFromUniverse': missing}

    out = {
        'asOf': {'STIP': stip_m.get('asOf'), 'TIP': tip_m.get('asOf'), 'DFIP': dfip_m.get('asOf'), 'LTPZ': ltpz_m.get('asOf')},
        'sources': {'DFIP': dfip_m.get('url'), 'LTPZ': ltpz_m.get('url')},
        'generatedAt': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
        'universe': sorted(universe.values(), key=lambda x: x['maturity']),
        'funds': funds,
        'checks': checks,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w') as fh:
        json.dump(out, fh, indent=1)
    print(f'wrote {OUT}: {len(universe)} bonds in universe')
    for tk, c in checks.items():
        print(f'  {tk}: {c["nHoldings"]} holdings, bond weight {c["bondWeightBeforeNormalize"]:.4f}, missing {c["missingFromUniverse"] or "none"}')

if __name__ == '__main__':
    main()
