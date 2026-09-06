const assert = require('node:assert/strict');
const Search=require('../search-core');
const data=require('../data/services.json').services;
const cases=require('./backtest_cases.json');
let count=0;
const ids=q=>Search.localRetrieve(q,data,8).map(s=>s.id);
for (const q of ['반려동물 보험','여권 케이스 추천','인감도장 구매','전기차 충전소','공영주차장 정기권','한부모 가족 증명서','사업자등록증 발급','취업증명서','냉장고 구매','주소 검색']) {assert.deepEqual(ids(q),[],q);count++;}
assert(!ids('코로나 예방접종').includes('PET-001'));count++;
for(const q of ['4111 1111 1111 1111','123-456-789012','１２３４５６７８９０１２３４５６','010\u200b-1234-5678','900101–1234567']) {assert(Search.containsSensitiveInfo(q),q);count++;}
for(const url of ['javascript:alert(1)','data:text/html,a','file:///test','https://u:p@example.org','http://www.gov.kr']){assert.equal(Search.safeHttpsUrl(url),'');count++;}
for(const q of cases.map(c=>c.q)) {const first=ids(q);ids('소파 버리고 싶어요');assert.deepEqual(ids(q),first);count++;}
const snapshot=JSON.stringify(data);for(const q of cases.map(c=>c.q))ids(q);assert.equal(JSON.stringify(data),snapshot);count++;
console.log(JSON.stringify({ok:true,assertions:count,cases:cases.length}));
