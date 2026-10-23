#!/usr/bin/env python3
"""Reference implementation of the sheet's analytics, used to verify the dashboard.

Replicates 'Allocate By Percent': years-to-maturity via Excel YEARFRAC basis 0
(US 30/360) from an as-of date, per-fund look-through characteristics, blended
statistics, 31-year ladder, and maturity buckets.
"""
import json, datetime as dt

def yearfrac_30_360_us(d1, d2):
    y1, m1, dd1 = d1.year, d1.month, d1.day
    y2, m2, dd2 = d2.year, d2.month, d2.day
    if dd1 == 31: dd1 = 30
    if dd2 == 31 and dd1 == 30: dd2 = 30
    return ((y2 - y1) * 360 + (m2 - m1) * 30 + (dd2 - dd1)) / 360.0

def analyze(data, weights, size, today, fees=None):
    """weights: {'STIP': w, 'DFIP': w, 'LTPZ': w} summing to 1. Returns dict of outputs."""
    uni = {u['cusip']: u for u in data['universe']}
    for u in uni.values():
        m = dt.date.fromisoformat(u['maturity'])
        u['_ytm_years'] = yearfrac_30_360_us(today, m)
        u['_year'] = m.year
    fees = fees or {tk: data['funds'][tk]['expense'] for tk in weights}
    rows = []  # (ticker, cusip, fund_weight, blended_weight)
    for tk, fw in weights.items():
        for h in data['funds'][tk]['holdings']:
            rows.append((tk, h['cusip'], h['weight'], h['weight'] * fw))
    def wavg(sel, key):
        num = sum(w * uni[c][key] for tk, c, w, _ in sel); den = sum(w for tk, c, w, _ in sel)
        return num / den if den else float('nan')
    fund_chars = {}
    for tk in weights:
        sel = [r for r in rows if r[0] == tk]
        fund_chars[tk] = {'avgMat': wavg(sel, '_ytm_years'), 'avgDur': wavg(sel, 'realDur'), 'ytm': wavg(sel, 'realYtm') / 100,
                          'value': weights[tk] * size}
    blended = {
        'avgDur': sum(bw * uni[c]['realDur'] for _, c, _, bw in rows),
        'avgMat': sum(bw * uni[c]['_ytm_years'] for _, c, _, bw in rows),
        'avgCoupon': sum(bw * uni[c]['coupon'] for _, c, _, bw in rows) / 100,
        'realYtm': sum(bw * uni[c]['realYtm'] for _, c, _, bw in rows) / 100,
        'fees': sum(weights[tk] * fees[tk] for tk in weights),
    }
    blended['realYtmNet'] = blended['realYtm'] - blended['fees']
    ladder = {}
    for _, c, _, bw in rows:
        y = uni[c]['_year']; ladder[y] = ladder.get(y, 0) + bw
    y0 = today.year
    ladder_rows = [(y0 + i, ladder.get(y0 + i, 0.0)) for i in range(31)]
    buckets = {}
    edges = [(0, 5, '0-5'), (5, 10, '5-10'), (10, 15, '10-15'), (15, 20, '15-20'), (20, 25, '20-25'), (25, 999, '25+')]
    for lo, hi, label in edges:  # sheet buckets by ladder index (year offset), not by exact tenor
        buckets[label] = sum(w for i, (y, w) in enumerate(ladder_rows) if lo <= i < hi)
    return {'fund': fund_chars, 'blended': blended, 'ladder': ladder_rows, 'buckets': buckets, 'ladderTotal': sum(ladder.values())}

def solve_dfip_for_wam(data, stip_w, target_wam, size, today):
    """Given a fixed STIP weight, find DFIP weight (LTPZ = 1 - STIP - DFIP) hitting target WAM. WAM is linear in weights."""
    a = analyze(data, {'STIP': stip_w, 'DFIP': 1 - stip_w, 'LTPZ': 0.0}, size, today)['blended']['avgMat']
    b = analyze(data, {'STIP': stip_w, 'DFIP': 0.0, 'LTPZ': 1 - stip_w}, size, today)['blended']['avgMat']
    if a == b: return None
    t = (target_wam - b) / (a - b)          # fraction of the non-STIP sleeve in DFIP
    dfip = t * (1 - stip_w)
    return max(0.0, min(1 - stip_w, dfip))

if __name__ == '__main__':
    import sys
    data = json.load(open(sys.argv[1] if len(sys.argv) > 1 else 'data/tips_data.json'))
    today = dt.date.today()
    r = analyze(data, {'STIP': 0.25, 'DFIP': 0.60, 'LTPZ': 0.15}, 500000, today)
    print(json.dumps({'fund': r['fund'], 'blended': r['blended'], 'buckets': r['buckets'], 'ladderTotal': r['ladderTotal']}, indent=1))
