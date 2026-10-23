// Browser port of engine.py (the sheet's 'Allocate By Percent' analytics).
// Inlined into the dashboard by make_dashboard.py; node can require() it to
// check results against engine.py.

function parseISO(s) { const [y, m, d] = s.split('-').map(Number); return { y, m, d }; }

// Excel YEARFRAC basis 0 (US 30/360), as in engine.yearfrac_30_360_us
function yearfrac30360(a, b) {
  let d1 = a.d, d2 = b.d;
  if (d1 === 31) d1 = 30;
  if (d2 === 31 && d1 === 30) d2 = 30;
  return ((b.y - a.y) * 360 + (b.m - a.m) * 30 + (d2 - d1)) / 360;
}

const BUCKETS = [[0, 5, '0-5'], [5, 10, '5-10'], [10, 15, '10-15'], [15, 20, '15-20'], [20, 25, '20-25'], [25, 999, '25+']];

// weights: {STIP, DFIP, LTPZ} as fractions summing to 1; today: 'YYYY-MM-DD'
function analyze(data, weights, size, today) {
  const t = parseISO(today);
  const uni = {};
  for (const u of data.universe) {
    const m = parseISO(u.maturity);
    uni[u.cusip] = Object.assign({}, u, { ytmYears: yearfrac30360(t, m), year: m.y });
  }
  const tickers = Object.keys(weights);
  const rows = [];  // {tk, cusip, fw (weight in fund), bw (weight in blend)}
  for (const tk of tickers)
    for (const h of data.funds[tk].holdings)
      rows.push({ tk, cusip: h.cusip, fw: h.weight, bw: h.weight * weights[tk] });

  const fund = {};
  for (const tk of tickers) {
    const sel = rows.filter(r => r.tk === tk);
    const den = sel.reduce((s, r) => s + r.fw, 0);
    const wavg = k => sel.reduce((s, r) => s + r.fw * uni[r.cusip][k], 0) / den;
    fund[tk] = { avgMat: wavg('ytmYears'), avgDur: wavg('realDur'), ytm: wavg('realYtm') / 100,
                 expense: data.funds[tk].expense, weight: weights[tk], value: weights[tk] * size };
  }
  const sum = k => rows.reduce((s, r) => s + r.bw * uni[r.cusip][k], 0);
  const fees = tickers.reduce((s, tk) => s + weights[tk] * data.funds[tk].expense, 0);
  const blended = { avgDur: sum('realDur'), avgMat: sum('ytmYears'), avgCoupon: sum('coupon') / 100,
                    realYtm: sum('realYtm') / 100, fees };
  blended.realYtmNet = blended.realYtm - fees;

  // 31-year ladder from today's year, split by fund
  const ladder = [];
  for (let i = 0; i < 31; i++) ladder.push({ year: t.y + i, total: 0, byFund: Object.fromEntries(tickers.map(k => [k, 0])) });
  let ladderTotal = 0;
  for (const r of rows) {
    const i = uni[r.cusip].year - t.y;
    ladderTotal += r.bw;
    if (i >= 0 && i < 31) { ladder[i].total += r.bw; ladder[i].byFund[r.tk] += r.bw; }
  }
  // the sheet buckets by ladder index (year offset), not by exact tenor
  const buckets = BUCKETS.map(([lo, hi, label]) => ({ label, w: ladder.filter((_, i) => lo <= i && i < hi).reduce((s, x) => s + x.total, 0) }));

  // look-through by bond
  const bonds = {};
  for (const r of rows) {
    const b = bonds[r.cusip] || (bonds[r.cusip] = Object.assign({}, uni[r.cusip], { byFund: {}, w: 0 }));
    b.byFund[r.tk] = (b.byFund[r.tk] || 0) + r.bw; b.w += r.bw;
  }
  const bondList = Object.values(bonds).sort((a, b) => a.maturity < b.maturity ? -1 : 1);
  return { fund, blended, ladder, buckets, ladderTotal, bonds: bondList };
}

// Fixed STIP weight; DFIP weight (LTPZ = remainder) that hits target WAM. WAM is linear in weights.
function solveDfipForWam(data, stipW, targetWam, size, today) {
  const a = analyze(data, { STIP: stipW, DFIP: 1 - stipW, LTPZ: 0 }, size, today).blended.avgMat;
  const b = analyze(data, { STIP: stipW, DFIP: 0, LTPZ: 1 - stipW }, size, today).blended.avgMat;
  if (a === b) return null;
  const t = (targetWam - b) / (a - b);
  return Math.max(0, Math.min(1 - stipW, t * (1 - stipW)));
}

if (typeof module !== 'undefined') module.exports = { analyze, solveDfipForWam, yearfrac30360 };
