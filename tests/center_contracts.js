const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const sandbox = {window: {}, console};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../js/centers.js'), 'utf8'), sandbox);
const Center = sandbox.window.LifeNaviCenters;
const centers = JSON.parse(fs.readFileSync(path.join(__dirname, '../data/welfare-centers.json'), 'utf8')).centers;

let assertions = 0;
function equal(actual, expected, message) { assert.equal(actual, expected, message); assertions++; }
function throwsCode(fn, code) { assert.throws(fn, error => error && error.code === code); assertions++; }

for (const address of [
  '상신하길로 274',
  '화성시 상신하길로 274',
  '경기도 화성시 만세구 향남읍 상신하길로 274',
  '  상신하길로   274  ',
  '상신하길로274번길 10',
]) equal(Center.knownJurisdiction(address, centers)?.area, '향남읍', address);
equal(Center.knownJurisdiction('향남읍', centers)?.area, '향남읍', 'explicit area');
equal(Center.knownJurisdiction('수원시 향남읍', centers), null, 'other city must not match explicit area');
equal(Center.knownJurisdiction('상신하길 274', centers), null, 'unverified road must not match');

const exact = {latitude:37.132440274920086, longitude:126.92033947505901, accuracy:15};
equal(Center.nearest(exact, centers).length, 1, 'default exposes one result');
equal(Center.nearest(exact, centers)[0].area, '향남읍', 'nearest exact center');
equal(Center.nearest(exact, centers, 3).length, 3, 'explicit diagnostic limit');
equal(Center.trustedNearest(exact, centers).area, '향남읍', 'trusted exact center');
equal(Center.trustedNearest(exact, centers).accuracyLow, false, 'good accuracy is not flagged');
equal(Center.trustedNearest({...exact, accuracy:2500}, centers).area, '향남읍', 'low accuracy still returns the nearest center');
equal(Center.trustedNearest({...exact, accuracy:2500}, centers).accuracyLow, true, 'low accuracy is flagged, not thrown');
equal(Center.trustedNearest({latitude:37.7, longitude:126.7, accuracy:10}, centers).accuracyLow, false, 'far but valid coordinates still resolve to nearest');
throwsCode(() => Center.trustedNearest({latitude:0, longitude:0, accuracy:10}, centers), 'LOCATION_INVALID');

// 15 independent order perturbations: center choice must never depend on source ordering.
for (let run = 0; run < 15; run++) {
  const shuffled = centers.slice().sort((a, b) => ((a.area.charCodeAt(run % a.area.length) + run) % 7) - ((b.area.charCodeAt(run % b.area.length) + run) % 7));
  equal(Center.trustedNearest(exact, shuffled).area, '향남읍', 'stable run ' + (run + 1));
  equal(Center.knownJurisdiction('상신하길로 274', shuffled)?.area, '향남읍', 'address run ' + (run + 1));
}

console.log(JSON.stringify({ok:true, independent_runs:15, assertions}));
