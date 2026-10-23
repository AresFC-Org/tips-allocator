#!/usr/bin/env python3
"""Fetch STIP, TIP, DFIP and LTPZ holdings over plain HTTP (no browser) into data/raw/<date>/.

Usage:  python3 fetch_direct.py [--date YYYY-MM-DD] [--out DIR]

Writes STIP.psv, TIP.psv, DFIP.psv and LTPZ.psv in the same format as the
STAGE_ISHARES / STAGE_DFIP / STAGE_LTPZ stages in fetcher.js, so build_data.py
reads them unchanged. Standard library only, so it runs in a cloud session or
on a schedule.

  --date  holdings date to fetch (default: PIMCO's latest day). DFIP steps back
          up to 7 days if Dimensional has no file for that date (weekends, holidays).
          iShares only serves its latest holdings, so STIP/TIP are skipped when
          they are newer than --date (they would not belong in that folder).
  --out   output folder (default: data/raw/<date>)

Endpoints (verified 2026-10-21; see fetcher.js for the browser versions):
  https://www.ishares.com/us/products/239450/ishares-0-5-year-tips-bond-etf/latest-holdings.csv
  https://www.ishares.com/us/products/239467/ishares-tips-bond-etf/latest-holdings.csv
  https://tools-blob.dimensional.com/etf/YYYYMMDD/DFIP.csv
  https://fund-ui.pimco.com/fund-detail-api/api/as-of-date?cusip=72201R304
  https://fund-ui.pimco.com/fund-detail-api/api/funds/72201R304/topTenHoldings/export?asOfDate=YYYY-MM-DD
"""
import argparse, csv, datetime as dt, io, json, os, re, sys, urllib.error, urllib.request, zipfile
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(ROOT, 'data', 'raw')

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'
PIMCO_CUSIP = '72201R304'
PIMCO_BASE = 'https://fund-ui.pimco.com/fund-detail-api/api/'
PIMCO_HEADERS = {'Client': 'WEB', 'CountryCode': 'US', 'LangCode': 'en', 'UserRole': 'FI',
                 'Accept': 'application/json, text/plain, */*'}
NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}

def get(url, headers=None):
    req = urllib.request.Request(url, headers={'User-Agent': UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()

def num(s):
    """Mirror fetcher.js num(): strip , % $ and spaces, print like a JS Number."""
    if s is None:
        return ''
    t = re.sub(r'[,%$\s]', '', str(s))
    if t in ('', '-', '—'):
        return ''
    try:
        v = float(t)
    except ValueError:
        return ''
    return str(int(v)) if v.is_integer() else repr(v)

def iso_from_us(s):
    m = re.fullmatch(r'(\d{2})/(\d{2})/(\d{4})', s or '')
    return f'{m[3]}-{m[1]}-{m[2]}' if m else ''

def iso_from_long(s):
    """'Sep 18, 2026' -> '2026-09-18' (fetcher.js isoFromLong)."""
    try:
        return dt.datetime.strptime((s or '').strip(), '%b %d, %Y').date().isoformat()
    except ValueError:
        return ''

ISHARES = {
    'STIP': 'https://www.ishares.com/us/products/239450/ishares-0-5-year-tips-bond-etf/latest-holdings.csv',
    'TIP': 'https://www.ishares.com/us/products/239467/ishares-tips-bond-etf/latest-holdings.csv',
}

def parse_ishares(text):
    rows = list(csv.reader(io.StringIO(text)))
    as_of = iso_from_long(next((x for x in rows if x and x[0] == 'Fund Holdings as of'), ['', ''])[1])
    hi = next(i for i, x in enumerate(rows) if x and x[0] == 'Name' and 'CUSIP' in x)
    H = rows[hi]; c = H.index
    lines = []
    for x in rows[hi + 1:]:
        if len(x) < len(H) or not x[c('CUSIP')]:
            continue
        lines.append('|'.join([x[c('CUSIP')], num(x[c('Market Value')]), num(x[c('Weight (%)')]), num(x[c('Price')]),
                               iso_from_long(x[c('Maturity')]), num(x[c('Coupon (%)')]), num(x[c('Real Duration')]),
                               num(x[c('Real YTM (%)')]), num(x[c('Par Value')]), x[c('Sector')], x[c('Name')]]))
    return as_of, f'asOf={as_of}\ncusip|mv|weight|price|maturity|coupon|realDur|realYtm|par|sector|name\n' + '\n'.join(lines)

def fetch_ishares(tk):
    return parse_ishares(get(ISHARES[tk]).decode('utf-8-sig'))

def fetch_dfip(date):
    for back in range(8):
        d = date - dt.timedelta(days=back)
        url = f'https://tools-blob.dimensional.com/etf/{d:%Y%m%d}/DFIP.csv'
        try:
            text = get(url).decode('utf-8-sig')
            break
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
    else:
        raise RuntimeError(f'no DFIP file within 7 days of {date}')
    rows = list(csv.reader(io.StringIO(text)))
    H = rows[0]; c = H.index
    lines = ['|'.join(x[c(k)] for k in ('identifier', 'weight', 'market_value', 'coupon_rate', 'maturity_date', 'shares', 'description'))
             for x in rows[1:] if len(x) >= len(H) and x[c('identifier')]]
    as_of = rows[1][c('date')]
    return as_of, f'url={url}\nasOf={as_of}\ncusip|weight|mv|coupon|maturity|par|desc\n' + '\n'.join(lines)

def pimco_latest_day():
    return json.loads(get(PIMCO_BASE + 'as-of-date?cusip=' + PIMCO_CUSIP, PIMCO_HEADERS))['latestDay']

def xlsx_rows(blob):
    """First worksheet as a list of {column letter: cell text}."""
    z = zipfile.ZipFile(io.BytesIO(blob))
    ss = []
    if 'xl/sharedStrings.xml' in z.namelist():
        for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si', NS):
            ss.append(''.join(t.text or '' for t in si.iter('{%s}t' % NS['m'])))
    rows = []
    for row in ET.fromstring(z.read('xl/worksheets/sheet1.xml')).iter('{%s}row' % NS['m']):
        cells = {}
        for cell in row.findall('m:c', NS):
            col = re.match(r'[A-Z]+', cell.get('r'))[0]
            v = cell.find('m:v', NS)
            if cell.get('t') == 'inlineStr':
                cells[col] = ''.join(t.text or '' for t in cell.iter('{%s}t' % NS['m']))
            elif v is not None:
                cells[col] = ss[int(v.text)] if cell.get('t') == 's' else v.text
        rows.append(cells)
    return rows

def fetch_ltpz(date):
    url = f'{PIMCO_BASE}funds/{PIMCO_CUSIP}/topTenHoldings/export?asOfDate={date}'
    rows = xlsx_rows(get(url, PIMCO_HEADERS))
    hdr = next(r for r in rows if r.get('A') == '% of Net Assets')
    cols = {v: k for k, v in hdr.items()}
    g = lambda r, n: r.get(cols[n])
    lines = []
    for r in rows:
        if r is hdr or not g(r, 'Description') or str(r.get('A', '')).startswith('AsOfDate'):
            continue
        cu = g(r, 'CUSIP')
        if not cu:
            continue
        lines.append('|'.join(['' if cu == '—' else cu, num(g(r, '% of Net Assets')), num(g(r, 'Market Value (USD)')),
                               g(r, 'Security Type') or '', num(g(r, 'Coupon Rate')), iso_from_us(g(r, 'Maturity Date')),
                               num(g(r, 'Notional/Par Value Quantity/Units')), num(g(r, 'Security Price')), g(r, 'Description')]))
    m = re.search(r'AsOfDate:\s*(\d{2})/(\d{2})/(\d{4})', rows[0].get('A', ''))
    as_of = f'{m[3]}-{m[1]}-{m[2]}' if m else str(date)
    return as_of, f'url={url}\nasOf={as_of}\ncusip|pct|mv|type|coupon|maturity|par|price|desc\n' + '\n'.join(lines)

def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--date', type=dt.date.fromisoformat)
    ap.add_argument('--out')
    a = ap.parse_args()
    date = a.date or dt.date.fromisoformat(pimco_latest_day())
    out = a.out or os.path.join(RAW, str(date))
    os.makedirs(out, exist_ok=True)
    for tk, fn in (('STIP', fetch_ishares), ('TIP', fetch_ishares), ('DFIP', fetch_dfip), ('LTPZ', fetch_ltpz)):
        as_of, text = fn(tk) if fn is fetch_ishares else fn(date)
        if fn is fetch_ishares and as_of > str(date):
            print(f'{tk}: skipped, iShares only serves its latest holdings (asOf {as_of}), newer than {date}')
            continue
        with open(os.path.join(out, tk + '.psv'), 'w', encoding='utf-8') as fh:
            fh.write(text + '\n')
        n = text.count('\n') - 2
        flag = '' if as_of == str(date) else f'  (requested {date})'
        print(f'{tk}: {n} rows, asOf {as_of}{flag} -> {os.path.join(out, tk + ".psv")}')
        if n < 5:
            sys.exit(f'{tk}: only {n} rows; source format may have changed')

if __name__ == '__main__':
    main()
