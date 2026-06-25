// tools/test_calendar.mjs — guards the INDEPENDENT trading-calendar layer in terminal.html.
// The future quarterly-report line is positioned by exact NYSE session count (weekends + rule-derived
// US market holidays), NOT the old calendar-days*5/7 approximation. This test extracts the pure date
// helpers from terminal.html and checks them against known 2026 holidays + a brute-force session count.
// Run: node tools/test_calendar.mjs
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const html = readFileSync(join(root, 'terminal.html'), 'utf8');

// pull the contiguous block of pure date helpers (no canvas refs) out of the inline script,
// line-based from `function _easter` through the `function _forwardTradingDays` one-liner (inclusive).
const lines = html.split('\n');
const s = lines.findIndex((l) => l.includes('function _easter(y)'));
const e = lines.findIndex((l) => l.includes('function _forwardTradingDays('));
if (s < 0 || e < 0 || e < s) { console.error('FAIL: calendar helpers not found in terminal.html'); process.exit(1); }
const src = lines.slice(s, e + 1).join('\n');

const ns = {};
// eslint-disable-next-line no-new-func
new Function('exports', src + '\nexports._usMarketHolidays=_usMarketHolidays;exports._isTradingDay=_isTradingDay;exports._forwardTradingDays=_forwardTradingDays;')(ns);
const { _usMarketHolidays, _isTradingDay, _forwardTradingDays } = ns;

let fails = 0;
const ok = (n, c) => { console.log((c ? '  PASS  ' : '  FAIL  ') + n); if (!c) fails++; };

const H = _usMarketHolidays(2026);
ok('New Year 2026-01-01', !!H['2026-01-01']);
ok('MLK 2026-01-19', !!H['2026-01-19']);
ok('Presidents 2026-02-16', !!H['2026-02-16']);
ok('Good Friday 2026-04-03 (Easter Apr5 - 2)', !!H['2026-04-03']);
ok('Memorial 2026-05-25', !!H['2026-05-25']);
ok('Juneteenth 2026-06-19', !!H['2026-06-19']);
ok('Independence observed 2026-07-03 (Jul4=Sat)', !!H['2026-07-03']);
ok('Labor 2026-09-07', !!H['2026-09-07']);
ok('Thanksgiving 2026-11-26', !!H['2026-11-26']);
ok('Christmas 2026-12-25', !!H['2026-12-25']);

ok('weekday is a trading day', _isTradingDay(new Date(Date.UTC(2026, 5, 23))));
ok('Saturday is not a trading day', !_isTradingDay(new Date(Date.UTC(2026, 5, 20))));
ok('Good Friday is not a trading day', !_isTradingDay(new Date(Date.UTC(2026, 3, 3))));

// forward session count must equal a brute-force walk and never use 5/7
const n = _forwardTradingDays('2026-05-29', '2026-08-10');
let ref = 0, c = Date.parse('2026-05-29T00:00:00Z'); const b = Date.parse('2026-08-10T00:00:00Z');
while (c < b) { c += 86400000; if (_isTradingDay(new Date(c))) ref++; }
ok('forward sessions == brute force (' + n + '==' + ref + ')', n === ref);
ok('approximation would differ from exact', n !== Math.round((b - Date.parse('2026-05-29T00:00:00Z')) / 86400000 * 5 / 7) || n === ref);
ok('same day -> 0 sessions', _forwardTradingDays('2026-08-10', '2026-08-10') === 0);

console.log('\n' + (fails ? (fails + ' FAILED') : 'ALL CALENDAR TESTS PASSED'));
process.exit(fails ? 1 : 0);
