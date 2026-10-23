// TIPS ETF Analyzer: in-browser fetch stages (run in the Claude built-in browser).
//
// Each stage runs on the matching site's origin so the site's own CORS and
// cookie rules apply, and returns a compact pipe-delimited text block that is
// saved verbatim as data/raw/<asOf>/<TICKER>.psv. build_data.py assembles the
// four files into data/tips_data.json. Nothing is downloaded to disk by the
// browser; no save dialogs.
//
// Stage 1 (any ishares.com page):      STAGE_ISHARES  -> STIP.psv and TIP.psv (split on "=====")
// Stage 2 (DFIP fund page, dimensional.com):  STAGE_DFIP -> DFIP.psv
// Stage 3 (LTPZ fund page, pimco.com):   STAGE_LTPZ  -> LTPZ.psv
//
// Verified endpoints (2026-09-21):
//   https://www.ishares.com/us/products/239450/ishares-0-5-year-tips-bond-etf/latest-holdings.csv
//   https://www.ishares.com/us/products/239467/ishares-tips-bond-etf/latest-holdings.csv
//   https://tools-blob.dimensional.com/etf/YYYYMMDD/DFIP.csv   (link discovered on the fund page)
//   https://fund-ui.pimco.com/fund-detail-api/api/as-of-date?cusip=72201R304
//   https://fund-ui.pimco.com/fund-detail-api/api/funds/72201R304/topTenHoldings/export?asOfDate=YYYY-MM-DD
//     (returns the full holdings xlsx despite the name; needs headers Client=WEB, CountryCode=US, LangCode=en, UserRole=FI)

const HELPERS = String.raw`
function parseCsv(text){const rows=[];let row=[],field='',q=false;for(let i=0;i<text.length;i++){const c=text[i];if(q){if(c==='"'){if(text[i+1]==='"'){field+='"';i++;}else q=false;}else field+=c;}else if(c==='"')q=true;else if(c===','){row.push(field);field='';}else if(c==='\n'||c==='\r'){if(c==='\r'&&text[i+1]==='\n')i++;row.push(field);rows.push(row);row=[];field='';}else field+=c;}if(field.length||row.length){row.push(field);rows.push(row);}return rows;}
const num=s=>{if(s==null)return '';const t=String(s).replace(/[,%$\s]/g,'');if(t===''||t==='-'||t==='—')return '';const v=Number(t);return isFinite(v)?v:'';};
const isoFromLong=s=>{const d=new Date(s+' UTC');return isNaN(d)?'':d.toISOString().slice(0,10);};
const isoFromUS=s=>{const m=/^(\d{2})\/(\d{2})\/(\d{4})$/.exec(s||'');return m?m[3]+'-'+m[1]+'-'+m[2]:'';};
`;

const STAGE_ISHARES = HELPERS + String.raw`
async function pull(url){const r=await fetch(url,{credentials:'omit'});if(!r.ok)throw new Error(url+' -> '+r.status);const rows=parseCsv(await r.text());const asOf=isoFromLong((rows.find(x=>x[0]==='Fund Holdings as of')||[])[1]);const hi=rows.findIndex(x=>x[0]==='Name'&&x.includes('CUSIP'));const H=rows[hi];const c=n=>H.indexOf(n);const lines=[];for(const x of rows.slice(hi+1)){if(x.length<H.length||!x[c('CUSIP')])continue;lines.push([x[c('CUSIP')],num(x[c('Market Value')]),num(x[c('Weight (%)')]),num(x[c('Price')]),isoFromLong(x[c('Maturity')]),num(x[c('Coupon (%)')]),num(x[c('Real Duration')]),num(x[c('Real YTM (%)')]),num(x[c('Par Value')]),x[c('Sector')],x[c('Name')]].join('|'));}return 'asOf='+asOf+'\ncusip|mv|weight|price|maturity|coupon|realDur|realYtm|par|sector|name\n'+lines.join('\n');}
const STIP=await pull('https://www.ishares.com/us/products/239450/ishares-0-5-year-tips-bond-etf/latest-holdings.csv');
const TIP=await pull('https://www.ishares.com/us/products/239467/ishares-tips-bond-etf/latest-holdings.csv');
STIP+'\n=====\n'+TIP
`;

const STAGE_DFIP = HELPERS + String.raw`
await new Promise(r=>setTimeout(r,1500));
const a=[...document.querySelectorAll('a')].map(x=>x.href).find(h=>/tools-blob\.dimensional\.com\/etf\/\d{8}\/DFIP\.csv/i.test(h));
if(!a) throw new Error('no DFIP link on page');
const r=await fetch(a); if(!r.ok) throw new Error(a+' -> '+r.status);
const rows=parseCsv(await r.text()); const H=rows[0]; const c=n=>H.indexOf(n);
const lines=rows.slice(1).filter(x=>x.length>=H.length&&x[c('identifier')]).map(x=>[x[c('identifier')],x[c('weight')],x[c('market_value')],x[c('coupon_rate')],x[c('maturity_date')],x[c('shares')],x[c('description')]].join('|'));
'url='+a+'\nasOf='+rows[1][c('date')]+'\ncusip|weight|mv|coupon|maturity|par|desc\n'+lines.join('\n')
`;

const STAGE_LTPZ = HELPERS + String.raw`
const cusip='72201R304';const H={Client:'WEB',CountryCode:'US',LangCode:'en',UserRole:'FI',Accept:'application/json, text/plain, */*'};const base='https://fund-ui.pimco.com/fund-detail-api/api/';
const ao=await fetch(base+'as-of-date?cusip='+cusip,{headers:H});const aoText=ao.ok?await ao.text():'';const mm=/"latestDay"\s*:\s*"(\d{4}-\d{2}-\d{2})"/.exec(aoText)||/(\d{4}-\d{2}-\d{2})/.exec(aoText);let asOf=mm?mm[1]:null;
if(!asOf) throw new Error('no as-of date');
const url=base+'funds/'+cusip+'/topTenHoldings/export?asOfDate='+asOf;
const r=await fetch(url,{headers:H});if(!r.ok)throw new Error('export '+r.status);
const buf=new Uint8Array(await r.arrayBuffer());const dv=new DataView(buf.buffer);const td=new TextDecoder();
async function inflate(u8){const ds=new DecompressionStream('deflate-raw');const w=ds.writable.getWriter();w.write(u8);w.close();return await new Response(ds.readable).text();}
const files={};let p=0;while(p<buf.length-4&&dv.getUint32(p,true)===0x04034b50){const method=dv.getUint16(p+8,true),csize=dv.getUint32(p+18,true),nlen=dv.getUint16(p+26,true),elen=dv.getUint16(p+28,true);const name=td.decode(buf.slice(p+30,p+30+nlen));const start=p+30+nlen+elen;let end=start+csize;if(csize===0){end=start;while(end<buf.length-4&&dv.getUint32(end,true)!==0x08074b50)end++;}const data=buf.slice(start,end);files[name]=method===8?await inflate(data):td.decode(data);p=end;if(csize===0)p+=16;}
const ss=[...files['xl/sharedStrings.xml'].matchAll(/<si>([\s\S]*?)<\/si>/g)].map(m=>[...m[1].matchAll(/<t[^>]*>([^<]*)<\/t>/g)].map(t=>t[1]).join(''));
const rowsX=[...files['xl/worksheets/sheet1.xml'].matchAll(/<row [^>]*>([\s\S]*?)<\/row>/g)].map(m=>{const cells={};for(const c of m[1].matchAll(/<c r="([A-Z]+)\d+"([^>]*)>(?:<v>([^<]*)<\/v>)?/g)){cells[c[1]]=/t="s"/.test(c[2])?ss[Number(c[3])]:c[3];}return cells;});
const hdr=rowsX.find(r=>r.A==='% of Net Assets');const cols=Object.fromEntries(Object.entries(hdr).map(([k,v])=>[v,k]));const g=(r,n)=>r[cols[n]];
const lines=[];for(const r of rowsX){if(r===hdr||!g(r,'Description')||String(r.A||'').startsWith('AsOfDate'))continue;const cu=g(r,'CUSIP');if(!cu)continue;lines.push([cu==='—'?'':cu,num(g(r,'% of Net Assets')),num(g(r,'Market Value (USD)')),g(r,'Security Type'),num(g(r,'Coupon Rate')),isoFromUS(g(r,'Maturity Date')),num(g(r,'Notional/Par Value Quantity/Units')),num(g(r,'Security Price')),g(r,'Description')].join('|'));}
const m2=/AsOfDate:\s*(\d{2})\/(\d{2})\/(\d{4})/.exec(rowsX[0].A||'');
'url='+url+'\nasOf='+(m2?m2[3]+'-'+m2[1]+'-'+m2[2]:asOf)+'\ncusip|pct|mv|type|coupon|maturity|par|price|desc\n'+lines.join('\n')
`;

if (typeof module !== 'undefined') module.exports = { STAGE_ISHARES, STAGE_DFIP, STAGE_LTPZ };
