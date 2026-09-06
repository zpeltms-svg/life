const fs = require('fs');
const path = require('path');
const Search = require('../search-core.js');
const services = JSON.parse(fs.readFileSync(path.join(__dirname, '../data/services.json'), 'utf8')).services;
const cases = JSON.parse(fs.readFileSync(path.join(__dirname, 'backtest_cases.json'), 'utf8'));

function seeded(seed) {
  return function () {
    seed |= 0; seed = seed + 0x6D2B79F5 | 0;
    let t = Math.imul(seed ^ seed >>> 15, 1 | seed);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}
function shuffle(array, seed) {
  const result = array.slice(); const rand = seeded(seed);
  for (let i = result.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1)); [result[i], result[j]] = [result[j], result[i]];
  }
  return result;
}
function idsFor(query, source) { return Search.localRetrieve(query, source, 8).map(s => s.id); }
function assert(condition, message) { if (!condition) throw new Error(message); }

const args = process.argv.slice(2);
const idx = args.indexOf('--rounds');
const rounds = idx >= 0 ? Number(args[idx + 1]) : 12;
const seedIdx = args.indexOf('--seed');
const baseSeed = seedIdx >= 0 ? Number(args[seedIdx + 1]) : 20260906;
if (!Number.isInteger(rounds) || rounds < 1 || rounds > 100) throw new Error('rounds must be 1..100');

const baseline = new Map(cases.map(tc => [tc.q, idsFor(tc.q, services)]));
const originalSnapshot = JSON.stringify(services);
let assertions = 0;
for (let round = 0; round < rounds; round++) {
  const shuffledServices = shuffle(services, baseSeed + round * 997);
  for (const tc of cases) {
    const ids = idsFor(tc.q, shuffledServices);
    const expectedOrder = baseline.get(tc.q);
    assert(JSON.stringify(ids) === JSON.stringify(expectedOrder), `[round ${round+1}] order drift: ${tc.q} => ${ids} vs ${expectedOrder}`); assertions++;
    if (tc.empty) { assert(ids.length === 0, `[round ${round+1}] expected empty: ${tc.q} => ${ids}`); assertions++; }
    for (const expected of tc.include || []) { assert(ids.includes(expected), `[round ${round+1}] missing ${expected}: ${tc.q} => ${ids}`); assertions++; }
    for (const excluded of tc.exclude || []) { assert(!ids.includes(excluded), `[round ${round+1}] unexpected ${excluded}: ${tc.q} => ${ids}`); assertions++; }
    if (tc.top) { assert(ids[0] === tc.top, `[round ${round+1}] expected top ${tc.top}: ${tc.q} => ${ids}`); assertions++; }
    if (tc.order) { assert(JSON.stringify(ids.slice(0,tc.order.length)) === JSON.stringify(tc.order), `[round ${round+1}] required workflow order: ${tc.q} => ${ids}`); assertions++; }
  }
  assert(JSON.stringify(services) === originalSnapshot, `[round ${round+1}] service mutation detected`); assertions++;
}

const piiCases = [
  '010-1234-5678 지원 알려줘','abc@example.com 청년 지원','900101-1234567 출산지원','900101-5234567 출산지원',
  '123-45-67890 창업','031-5189-1234 전입신고','02-1234-5678 민원','070-1234-5678 민원','0505-123-4567 민원','향남로 470 전입신고','향남읍 123-4 전입신고'
];
for (const q of piiCases) { assert(Search.containsSensitiveInfo(q), `PII miss: ${q}`); assertions++; }
const safeCases = ['화성으로 이사 왔어요','청년 창업 지원','동탄7동','향남읍 전입신고','2026-09-07 출산지원','12,090원 공공인턴'];
for (const q of safeCases) { assert(!Search.containsSensitiveInfo(q), `PII false positive: ${q}`); assertions++; }

const areas = ['향남읍','동탄1동','동탄7동','봉담읍','동탄10동'];
assert(Search.matchWelfareArea('경기도 화성시 만세구 향남읍 발안로 89', areas) === '향남읍', 'area 향남읍 mismatch'); assertions++;
assert(Search.matchWelfareArea('화성시 동탄구 동탄7동', areas) === '동탄7동', 'area 동탄7동 mismatch'); assertions++;
assert(Search.matchWelfareArea('화성시 동탄10동', areas) === '동탄10동', 'area specificity mismatch'); assertions++;
assert(Search.matchWelfareArea('동탄', areas) === '', 'ambiguous partial area should not auto-select'); assertions++;

assert(Search.safeHttpsUrl('https://www.gov.kr/path') === 'https://www.gov.kr/path', 'https URL rejected'); assertions++;
assert(Search.safeHttpsUrl('javascript:alert(1)', '') === '', 'javascript URL allowed'); assertions++;
assert(Search.safeHttpsUrl('https://user:pass@example.com/', '') === '', 'credential URL allowed'); assertions++;
assert(Search.sourceAgeDays('2026-09-07', Date.UTC(2026, 8, 7)) === 0, 'freshness day 0 mismatch'); assertions++;
assert(Search.sourceAgeDays('2026-09-02', Date.UTC(2026, 8, 7)) === 5, 'freshness day 5 mismatch'); assertions++;
assert(!Number.isFinite(Search.sourceAgeDays('bad-date', Date.UTC(2026, 8, 7))), 'invalid freshness date accepted'); assertions++;
assert(!Number.isFinite(Search.sourceAgeDays('2026-13-99', Date.UTC(2026, 8, 7))), 'invalid calendar date accepted'); assertions++;
assert(!Number.isFinite(Search.sourceAgeDays('2026-02-30', Date.UTC(2026, 8, 7))), 'rolled calendar date accepted'); assertions++;
assert(!Number.isFinite(Search.sourceAgeDays('2027-09-07', Date.UTC(2026, 8, 7))), 'future freshness date accepted'); assertions++;

console.log(JSON.stringify({ok:true, rounds, cases:cases.length, assertions, seed:baseSeed}));
