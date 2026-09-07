'use strict';

const SearchCore = window.LifeNaviSearch;
if (!SearchCore) throw new Error('검색 모듈을 불러오지 못했습니다.');

const form = document.querySelector('#guide-form');
const textarea = document.querySelector('#situation');
const submitBtn = document.querySelector('#submit-btn');
const results = document.querySelector('#results');
const list = document.querySelector('#result-list');
const noResult = document.querySelector('#no-result');
const analysisNote = document.querySelector('#analysis-note');
const resultPlan = document.querySelector('#result-plan');
const resetBtn = document.querySelector('#reset-btn');
const dialog = document.querySelector('#detail-dialog');
const dialogClose = document.querySelector('#detail-close');
const detailBody = document.querySelector('#detail-body');

let baseServices = [];
let welfareCenters = [];
let renderedServicesById = new Map();
let searchSequence = 0;

const welfareAreas = ['봉담읍', '우정읍', '향남읍', '남양읍', '매송면', '비봉면', '마도면', '송산면', '서신면', '팔탄면', '장안면', '양감면', '정남면', '새솔동', '진안동', '병점1동', '병점2동', '반월동', '기배동', '화산동', '동탄1동', '동탄2동', '동탄3동', '동탄4동', '동탄5동', '동탄6동', '동탄7동', '동탄8동', '동탄9동'];

async function fetchJson(url, options = {}, timeoutMs = 9000) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    const text = await response.text();
    let data = {};
    try { data = text ? JSON.parse(text) : {}; } catch (_) { throw new Error('서버 응답 형식을 확인해 주세요.'); }
    if (!response.ok) throw new Error(data.error || '요청을 처리하지 못했습니다.');
    return data;
  } catch (error) {
    if (error?.name === 'AbortError') throw new Error('응답 시간이 길어 요청을 종료했습니다. 잠시 후 다시 시도해 주세요.');
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}

async function fetchStaticJson(url, timeoutMs = 6000) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { cache: 'no-store', signal: controller.signal });
    if (!response.ok) throw new Error('정적 자료를 불러오지 못했습니다.');
    return await response.json();
  } catch (error) {
    if (error?.name === 'AbortError') throw new Error('기본 자료를 불러오는 시간이 너무 오래 걸립니다.');
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}

async function loadServices() {
  const [servicePayload, centerPayload] = await Promise.all([
    fetchStaticJson('./data/services.json'),
    fetchStaticJson('./data/welfare-centers.json').catch(() => ({centers: []})),
  ]);
  if (!Array.isArray(servicePayload.services) || !servicePayload.services.length) throw new Error('행정서비스 자료 형식이 올바르지 않습니다.');

  baseServices = Object.freeze(servicePayload.services.map((service) => Object.freeze({ ...service })));
  welfareCenters = (centerPayload.centers || []).map((center) => ({ ...center }));
  if (window.LifeNaviCenters && document.querySelector('#center-area')) {
    await window.LifeNaviCenters.init(welfareCenters, resolveTypedAddress, getCurrentPosition);
    if (!welfareCenters.length) document.querySelector('#center-status').textContent='센터 자료를 불러오지 못했습니다. 검색은 계속 이용할 수 있습니다. 민원안내 1577-4200';
  }
  document.querySelector('#service-count').textContent = `${baseServices.length}개 생활행정 서비스`;
}

function localRetrieve(query) {
  return SearchCore.localRetrieve(query, baseServices, 6);
}

async function aiRetrieve(query) {
  try {
    const data = await fetchJson('/api/guide', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query }),
    });
    if (!Array.isArray(data.service_ids)) return null;
    const index = new Map(baseServices.map((service) => [service.id, service]));
    return {
      services: data.service_ids.map((id) => index.get(id)).filter(service => service && !SearchCore.isExcluded(query, service)),
      note: '등록된 공식 자료를 바탕으로 안내합니다.',
      usedAi: data.used_ai === true,
    };
  } catch (_) {
    return null;
  }
}

async function publicDataRetrieve(query) {
  try {
    const data = await fetchJson('/api/public-services', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query }),
    });
    return {
      services: Array.isArray(data.services) ? data.services : [],
      configured: data.configured !== false,
      note: data.note || '',
    };
  } catch (_) {
    return { services: [], configured: false, note: '' };
  }
}

function safeHttpsUrl(value = '') {
  return SearchCore.safeHttpsUrl(value, '');
}

function sourceFreshness(service) {
  const threshold = Number.isFinite(Number(service.review_after_days)) ? Math.max(1, Number(service.review_after_days)) : 90;
  const ageDays = SearchCore.sourceAgeDays(service.source_checked);
  return { ageDays, threshold, stale: service.official_status === 'reference_only' || !Number.isFinite(ageDays) || ageDays > threshold };
}

function renderActionPlan(servicesToRender) {
  if (!resultPlan) return;
  const groupRank = { first: 0, document: 1, health: 1, everyday: 1, contact: 2, benefit: 3 };
  const ordered = servicesToRender.map((service, index) => ({ service, index }))
    .sort((a, b) => (groupRank[a.service.action_group] ?? 2) - (groupRank[b.service.action_group] ?? 2) || a.index - b.index)
    .map((item) => item.service);
  const labels = [];
  for (const service of ordered) {
    const label = String(service.action_label || '').trim();
    if (label && !labels.some((item) => item.label === label)) labels.push({label, title: service.title});
    if (labels.length >= 3) break;
  }
  if (!labels.length) { resultPlan.hidden = true; resultPlan.innerHTML = ''; return; }
  resultPlan.innerHTML = `<p>추천 흐름</p><ol>${labels.map((item, index) => `<li><span>${String(index + 1).padStart(2, '0')}</span><div><b>${escapeHtml(item.label)}</b><small>${escapeHtml(item.title)}</small></div></li>`).join('')}</ol>`;
  resultPlan.hidden = false;
}

function renderServices(servicesToRender) {
  list.innerHTML = '';
  renderedServicesById = new Map(servicesToRender.map((service) => [String(service.id), service]));
  noResult.hidden = servicesToRender.length > 0;
  renderActionPlan(servicesToRender);

  servicesToRender.forEach((service, index) => {
    const card = document.createElement('article');
    card.className = 'service-card';
    const online = service.online_application;
    const onlineUrl = online ? safeHttpsUrl(online.url) : '';
    const freshness = sourceFreshness(service);
    card.innerHTML = `
      <div>
        <div class="card-badges"><span class="badge">${escapeHtml(service.category_label)}</span>${service.action_label ? `<span class="action-badge">${escapeHtml(service.action_label)}</span>` : ''}</div>
        <h3>${index + 1}. ${escapeHtml(service.title)}</h3>
        <p>${escapeHtml(service.summary)}</p>
        ${onlineUrl ? `<a class="online-link" href="${escapeHtml(onlineUrl)}" target="_blank" rel="noopener noreferrer">● 온라인 신청 가능 <span>${escapeHtml(online.label)} ↗</span></a>` : ''}
        <div class="meta-row">
          <span><strong>처리기관</strong> ${escapeHtml(service.office)}</span>
          <span><strong>최근 자료확인</strong> ${escapeHtml(service.source_checked)}${freshness.stale ? ' · <b class="stale-warning">재확인 필요</b>' : ''}</span>
        </div>
      </div>
      <button class="detail-btn" type="button" data-id="${escapeHtml(service.id)}">자세히 보기 →</button>
    `;
    list.appendChild(card);
  });
}

function welfareOptions(placeholder = '읍·면·동 선택') {
  return `<option value="">${placeholder}</option>${welfareAreas.map((area) => `<option value="${escapeHtml(area)}">${escapeHtml(area)}</option>`).join('')}`;
}

function openDetail(service) {
  document.querySelector('#detail-category').textContent = service.category_label || '생활행정';
  document.querySelector('#detail-title').textContent = service.title || '서비스 안내';
  const method = (service.method || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('');
  const documents = (service.documents || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('');
  const isJurisdictionOffice = service.office_mode === 'jurisdiction';
  const isNationwideOffice = service.office_mode === 'nationwide_nearest';
  const onlineUrl = service.online_application ? safeHttpsUrl(service.online_application.url) : '';
  const sourceUrl = safeHttpsUrl(service.source_url);
  const freshness = sourceFreshness(service);

  const jurisdictionPanel = isJurisdictionOffice ? `
    <section class="application-panel jurisdiction-panel welfare-center-panel" data-service-id="${escapeHtml(service.id)}">
      <p>JURISDICTION OFFICE</p>
      <strong>주소지 관할 행정복지센터를 확인해 주세요.</strong>
      <label>현재 주소<input class="current-address" name="current-address" maxlength="120" placeholder="화성시 도로명주소 입력" autocomplete="street-address"></label>
      <div class="inline-actions">
        <button class="current-address-btn" type="button">현재 위치에서 가까운 센터 찾기 (관할 아님)</button>
        <button class="resolve-address-btn" type="button">입력 주소로 관할 찾기</button>
      </div>
      <label>화성시 읍·면·동<select class="welfare-area-select">${welfareOptions('관할 읍·면·동 선택')}</select></label>
      <button class="welfare-route-btn" type="button">선택한 관할 센터 길찾기</button>
      <small>실제 접수 가능 관할과 준비서류는 신청 전 공식 안내에서 다시 확인해 주세요.</small>
      <small class="map-privacy">주소·현재 위치는 관할 및 길찾기 계산을 위해 지도 API로 전송될 수 있으며 이 앱이 별도로 저장하지 않습니다.</small>
      <p class="route-status" aria-live="polite"></p>
    </section>` : '';

  const nationwidePanel = isNationwideOffice ? `
    <section class="application-panel visit-panel nearest-center-panel" data-service-id="${escapeHtml(service.id)}">
      <p>NATIONWIDE OFFICE</p>
      <strong>전국 읍·면·동에서 접수할 수 있습니다.</strong>
      <span>이 업무를 접수할 수 있는 행정복지센터 중 가장 가까운 곳을 찾습니다.</span>
      <button class="nearest-center-btn" type="button">현재 위치 기준 센터 찾기</button>
      <label>기기 위치가 다를 때 현재 주소<input class="nearest-origin-address" maxlength="120" placeholder="화성시 도로명주소 입력" autocomplete="street-address"></label>
      <button class="nearest-address-btn" type="button">입력 주소 기준 가장 가까운 접수처 찾기</button>
      <label>화성시 센터 직접 선택<select class="nearest-area-select">${welfareOptions('방문할 읍·면·동 선택')}</select></label>
      <button class="nearest-area-route-btn" type="button">선택한 센터 길찾기</button>
      <small class="map-privacy">현재 위치는 가까운 센터·길찾기 계산을 위해 지도 API로 전송될 수 있으며 이 앱이 별도로 저장하지 않습니다.</small>
      <p class="route-status" aria-live="polite"></p>
    </section>` : '';

  const online = service.online_application && onlineUrl ? `
    <section class="application-panel online-panel">
      <p>ONLINE APPLICATION</p>
      <strong>온라인 신청이 가능합니다.</strong>
      <a href="${escapeHtml(onlineUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(service.online_application.label)} <span>↗</span></a>
    </section>` : '';

  const visitDestinations = Array.isArray(service.visit_destinations) ? service.visit_destinations.filter((item) => item?.name && item?.address) : [];
  const singleVisit = service.visit_destination?.name && service.visit_destination?.address ? [service.visit_destination] : [];
  const destinations = visitDestinations.length ? visitDestinations : singleVisit;
  const visit = destinations.length ? `
    <section class="application-panel visit-panel" data-service-id="${escapeHtml(service.id)}">
      <p>OFFLINE VISIT</p>
      ${destinations.length > 1 ? `<strong>방문할 곳을 선택하세요.</strong><div class="destination-choices">${destinations.map((item) => `<button class="destination-choice" type="button" data-address="${escapeHtml(item.address)}"><b>${escapeHtml(item.name)}</b><span>${escapeHtml(item.address)}</span><em>현재 위치에서 예상시간 보기 →</em></button>`).join('')}</div>` : `<strong>${escapeHtml(destinations[0].name)}</strong><span>${escapeHtml(destinations[0].address)}</span><button class="route-btn" type="button" data-address="${escapeHtml(destinations[0].address)}">현재 위치에서 예상시간 보기</button>`}
      <form class="destination-form">
        <label>다른 장소 또는 화성시 읍·면·동 검색<input name="destination" class="area-search" list="welfare-area-options" maxlength="120" placeholder="읍·면·동 또는 도로명주소 입력" autocomplete="street-address"></label>
        <datalist id="welfare-area-options">${welfareAreas.map((area) => `<option value="${escapeHtml(area)}"></option>`).join('')}</datalist>
        <button type="submit">목적지 선택</button>
      </form>
      <p class="route-helper">읍·면·동을 입력하면 해당 행정복지센터를 선택하고, 도로명주소를 입력하면 그 주소로 길찾기합니다.</p>
      <small class="map-privacy">직접 입력한 목적지·현재 위치는 길찾기 계산을 위해 지도 API로 전송될 수 있으며 이 앱이 별도로 저장하지 않습니다.</small>
      <p class="route-status" aria-live="polite"></p>
    </section>` : service.offline_notice && !isJurisdictionOffice ? `
      <section class="application-panel jurisdiction-panel">
        <p>OFFLINE VISIT</p>
        <strong>방문 신청 전 접수기관 확인이 필요합니다.</strong>
        <span>${escapeHtml(service.offline_notice)}</span>
      </section>` : '';

  detailBody.innerHTML = `
    <p>${escapeHtml(service.summary)}</p>
    <div class="application-actions">${online}${visit}${jurisdictionPanel}${nationwidePanel}</div>
    <dl class="detail-grid">
      <dt>대상</dt><dd>${escapeHtml(service.who)}</dd>
      <dt>언제</dt><dd>${escapeHtml(service.when)}</dd>
      <dt>신청방법</dt><dd><ul>${method}</ul></dd>
      <dt>지금 할 일</dt><dd>${escapeHtml(service.now_action || service.action_label || '공식 안내 확인')}</dd>
      <dt>방문 여부</dt><dd>${escapeHtml(service.offline_notice || (onlineUrl ? '온라인 신청 대상·인증 조건을 확인하세요. 수령 등 방문이 필요한지 공식 안내를 확인하세요.' : '신청방법과 접수기관에 방문 필요 여부를 확인하세요.'))}</dd>
      <dt>준비사항</dt><dd><ul>${documents}</ul></dd>
      <dt>비용·수수료</dt><dd>${escapeHtml(service.fee || '공식 안내 확인')}</dd>
      <dt>처리기관</dt><dd>${escapeHtml(service.office)}</dd>
      <dt>처리기간</dt><dd>${escapeHtml(service.processing_time)}</dd>
      <dt>전화 문의</dt><dd>${escapeHtml(service.phone_label || '민원안내')} ${escapeHtml(service.phone || '1577-4200')}</dd>
      <dt>주의사항</dt><dd>${escapeHtml(service.caution || service.verification_note || '신청 전 공식 안내를 다시 확인하세요.')}</dd>
    </dl>
    <section class="task-checklist"><h3>처리 순서 · 준비 체크</h3>${(service.steps || service.method || []).map(item => `<label><input type="checkbox"><span>${escapeHtml(item)}</span></label>`).join('')}<small>체크한 내용은 저장하거나 전송하지 않습니다.</small></section>
    <div class="source-box">
      <strong>근거자료</strong>
      <p>${escapeHtml(service.source_name)}</p>
      <p>${sourceUrl ? `<a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer">공식 원문 열기</a>` : '<span class="stale-warning">공식 원문 링크 확인 필요</span>'}</p>
      <small>자료 확인일: ${escapeHtml(service.source_checked || '내용 검증일 미확인')}${service.retrieved_at ? ` · 조회일 ${escapeHtml(service.retrieved_at)}` : ''}${freshness.stale ? ` · <b class="stale-warning">${freshness.threshold}일 기준 재확인 필요</b>` : ''} · 실제 신청 전 최신 내용을 다시 확인하세요.</small>
    </div>
    <button class="print-detail" type="button">안내 인쇄·PDF 저장</button>
  `;
  dialog.showModal();
}

// 한 번의 getCurrentPosition은 첫 (부정확한) 측정을 그대로 돌려주는 경우가 많아,
// watchPosition으로 몇 초간 측정을 받아 가장 정확한 값을 사용한다.
function getCurrentPosition({ goodAccuracy = 70, settleMs = 3500, timeoutMs = 15000 } = {}) {
  return new Promise((resolve, reject) => {
    const geo = navigator.geolocation;
    if (!geo) return reject(new Error('이 브라우저에서는 현재 위치를 지원하지 않습니다.'));
    let best = null, done = false, settleTimer = 0, hardTimer = 0, watchId = 0;
    const stop = () => {
      done = true;
      window.clearTimeout(settleTimer);
      window.clearTimeout(hardTimer);
      try { geo.clearWatch(watchId); } catch (_) { /* noop */ }
    };
    const succeed = () => { if (!done) { stop(); resolve(best); } };
    hardTimer = window.setTimeout(() => {
      if (done) return;
      stop();
      if (best) resolve(best);
      else reject(Object.assign(new Error('현재 위치 신호가 약합니다. 실외에서 잠시 후 다시 시도하거나 주소를 입력해 주세요.'), { code: 3 }));
    }, timeoutMs);
    watchId = geo.watchPosition(
      (position) => {
        if (done) return;
        const accuracy = Number(position.coords.accuracy);
        if (!best || (Number.isFinite(accuracy) && accuracy < Number(best.coords.accuracy))) best = position;
        if (Number.isFinite(accuracy) && accuracy <= goodAccuracy) return succeed();
        if (!settleTimer) settleTimer = window.setTimeout(succeed, settleMs);
      },
      (error) => {
        if (done) return;
        if (best && error && error.code !== 1) return; // 일시적 오류는 무시하고 최선값 유지
        stop();
        reject(error);
      },
      { enableHighAccuracy: true, timeout: timeoutMs, maximumAge: 0 }
    );
  });
}

async function resolveTypedAddress(address) {
  return fetchJson('/api/address', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ address }),
  });
}

function centerForArea(area) {
  return welfareCenters.find((center) => center.area === area) || null;
}

async function showRoute(button, destinationQuery = '', originOverride = null, destinationCenter = null) {
  const panel = button.closest('.visit-panel, .welfare-center-panel');
  const status = panel?.querySelector('.route-status');
  if (!panel || !status) return;

  button.disabled = true;
  const originalLabel = button.textContent;
  const originalNodes = [...button.childNodes].map(node => node.cloneNode(true));
  button.textContent = '현재 위치 확인 중…';
  let directRouteHtml = '';
  try {
    const coords = originOverride || (await getCurrentPosition()).coords;
    if (destinationCenter) {
      window.LifeNaviCenters.trustedNearest(coords, welfareCenters);
      const directDistance = window.LifeNaviCenters.distanceKm(coords.latitude, coords.longitude, destinationCenter);
      button.dataset.fallbackDistance = String(directDistance);
      const appUrl = `nmap://route/car?slat=${encodeURIComponent(coords.latitude)}&slng=${encodeURIComponent(coords.longitude)}&sname=${encodeURIComponent('현재 위치')}&dlat=${encodeURIComponent(destinationCenter.lat)}&dlng=${encodeURIComponent(destinationCenter.lng)}&dname=${encodeURIComponent(destinationCenter.name)}&appname=${encodeURIComponent('com.hwaseong.life')}`;
      const webUrl = `https://map.naver.com/p/search/${encodeURIComponent(destinationCenter.address + ' ' + destinationCenter.name)}`;
      directRouteHtml = `<strong>직선거리 약 ${directDistance.toFixed(1)}km</strong><div class="route-links"><a href="${escapeHtml(appUrl)}" rel="noopener noreferrer">네이버 지도 앱 길안내 ↗</a><a href="${escapeHtml(webUrl)}" target="_blank" rel="noopener noreferrer">웹에서 센터 열기 ↗</a></div>`;
      status.innerHTML = directRouteHtml;
    }
    const route = await fetchJson('/api/route', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        service_id: panel.dataset.serviceId || '',
        destination_query: destinationQuery,
        origin: { latitude: coords.latitude, longitude: coords.longitude },
      }),
    }, 12000);

    const minutes = Math.max(1, Math.round(Number(route.duration_ms) / 60000));
    const kilometers = (Number(route.distance_m) / 1000).toFixed(1);
    panel._routeState = { route, origin: coords };
    const nmapUrl = `nmap://route/car?slat=${encodeURIComponent(coords.latitude)}&slng=${encodeURIComponent(coords.longitude)}&sname=${encodeURIComponent('현재 위치')}&dlat=${encodeURIComponent(route.latitude)}&dlng=${encodeURIComponent(route.longitude)}&dname=${encodeURIComponent(route.destination)}&appname=${encodeURIComponent('com.hwaseong.life')}`;
    const webSearchUrl = `https://map.naver.com/p/search/${encodeURIComponent(route.address || route.destination)}`;
    status.innerHTML = `<strong>자동차 약 ${minutes}분 · ${kilometers}km</strong><div class="route-links"><a href="${escapeHtml(nmapUrl)}" rel="noopener noreferrer">네이버 지도 앱 길안내 ↗</a><a href="${escapeHtml(webSearchUrl)}" target="_blank" rel="noopener noreferrer">웹에서 목적지 열기 ↗</a></div>`;
    await renderNaverMap(panel, route, coords);

    if (Array.isArray(route.routes) && route.routes.length > 1) {
      const options = route.routes.map((item, index) => {
        const optionMinutes = Math.max(1, Math.round(Number(item.duration_ms) / 60000));
        const optionKilometers = (Number(item.distance_m) / 1000).toFixed(1);
        return `<button class="route-option${index === 0 ? ' is-selected' : ''}" type="button" data-route-key="${escapeHtml(item.key)}"><b>${escapeHtml(item.label)}</b><span>약 ${optionMinutes}분 · ${optionKilometers}km</span></button>`;
      }).join('');
      status.insertAdjacentHTML('beforeend', `<div class="route-options" aria-label="경로 선택">${options}</div>`);
    }
    button.hidden = true;
  } catch (error) {
    const fallbackDistance = Number(button.dataset.fallbackDistance);
    if (directRouteHtml && Number.isFinite(fallbackDistance)) {
      status.innerHTML = directRouteHtml + '<small>도로 거리·예상시간을 불러오지 못해 직선거리를 표시했습니다. 위 링크의 네이버 지도 길안내는 바로 이용할 수 있습니다.</small>';
    } else {
      status.textContent = error?.code === 1 ? '거리를 계산하려면 현재 위치 사용을 허용해 주세요.' : (error.message || '경로 정보를 불러오지 못했습니다.');
    }
    if (!directRouteHtml && destinationQuery) {
      const link = document.createElement('a'); link.className='route-fallback'; link.textContent='네이버 지도에서 목적지·길찾기 열기 ↗'; link.href=`https://map.naver.com/p/search/${encodeURIComponent(destinationQuery)}`; link.target='_blank'; link.rel='noopener noreferrer'; status.append(document.createElement('br'),link);
    }
    button.disabled = false;
    button.replaceChildren(...originalNodes);
  }
}

let naverMapPromise = null;
function loadNaverMaps(clientId) {
  if (window.naver?.maps) return Promise.resolve();
  if (naverMapPromise) return naverMapPromise;
  naverMapPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script');
    const timer = window.setTimeout(() => {script.remove(); reject(new Error('지도 표시 시간이 초과되었습니다.'));}, 8000);
    script.id = 'naver-maps-sdk';
    script.src = `https://oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=${encodeURIComponent(clientId)}`;
    script.onload = () => { window.clearTimeout(timer); if(window.naver?.maps) resolve(); else {script.remove();reject(new Error('지도를 불러오지 못했습니다.'));} };
    script.onerror = () => {window.clearTimeout(timer);script.remove();reject(new Error('지도를 불러오지 못했습니다.'));};
    document.head.appendChild(script);
  }).catch(error => {naverMapPromise=null;throw error;});
  return naverMapPromise;
}

async function renderNaverMap(panel, route, origin) {
  if (!route.map_client_id || !Array.isArray(route.path) || route.path.length < 2) return;
  try {
    await loadNaverMaps(route.map_client_id);
    panel.querySelector('.naver-route-map')?.remove();
    const mapElement = document.createElement('div');
    mapElement.className = 'naver-route-map';
    mapElement.setAttribute('aria-label', `${route.destination} 자동차 경로 지도`);
    panel.appendChild(mapElement);
    const path = route.path.map(([longitude, latitude]) => new window.naver.maps.LatLng(latitude, longitude));
    const map = new window.naver.maps.Map(mapElement, { center: path[Math.floor(path.length / 2)], zoom: 13 });
    new window.naver.maps.Polyline({ map, path, strokeColor: '#2675d9', strokeWeight: 5, strokeOpacity: 0.85 });
    new window.naver.maps.Marker({ map, position: new window.naver.maps.LatLng(origin.latitude, origin.longitude), title: '현재 위치' });
    new window.naver.maps.Marker({ map, position: new window.naver.maps.LatLng(route.latitude, route.longitude), title: route.destination });
    const bounds = new window.naver.maps.LatLngBounds();
    path.forEach((position) => bounds.extend(position));
    map.fitBounds(bounds, { top: 26, right: 26, bottom: 26, left: 26 });
  } catch (_) {
    // 지도 표시 실패 시에도 텍스트 경로와 네이버 지도 링크는 유지합니다.
  }
}

async function setCurrentAddress(button) {
  const panel = button.closest('.welfare-center-panel');
  const select = panel.querySelector('.welfare-area-select');
  const status = panel.querySelector('.route-status');
  const originalLabel = button.textContent;
  button.disabled = true;
  button.textContent = '현재 위치 확인 중…';
  try {
    const { coords } = await getCurrentPosition();
    const center = window.LifeNaviCenters.trustedNearest(coords, welfareCenters);
    select.value = center.area;
    status.textContent = `현재 위치에서 직선거리 약 ${center.distance.toFixed(1)}km의 ${center.name}을 선택했습니다. 가까운 센터이며 주소지 관할 판정은 아닙니다.`;
  } catch (error) {
    status.textContent = error?.code === 1 ? '가까운 센터를 찾으려면 현재 위치 사용을 허용해 주세요.' : (error.message || '현재 위치의 가까운 센터를 찾지 못했습니다.');
  } finally {
    button.disabled = false;
    button.textContent = originalLabel;
  }
}

async function resolveAddressArea(button) {
  const panel = button.closest('.welfare-center-panel');
  const input = panel.querySelector('.current-address');
  const select = panel.querySelector('.welfare-area-select');
  const status = panel.querySelector('.route-status');
  const address = input.value.trim();
  if (!address) {
    status.textContent = '먼저 현재 주소를 입력해 주세요.';
    input.focus();
    return;
  }

  const originalLabel = button.textContent;
  button.disabled = true;
  button.textContent = '관할 확인 중…';
  try {
    const localCenter = window.LifeNaviCenters.knownJurisdiction(address, welfareCenters);
    if (localCenter) {
      select.value = localCenter.area;
      status.textContent = `${localCenter.area} 관할로 확인했습니다.`;
      return;
    }
    const data = await resolveTypedAddress(address);
    const area = SearchCore.matchWelfareArea(data.area || data.address || '', welfareAreas);
    if (!area) throw new Error('화성시 읍·면·동 관할을 확인하지 못했습니다. 도로명주소를 확인해 주세요.');
    input.value = data.address || address;
    select.value = area;
    status.textContent = `${area} 관할로 자동 선택했습니다.`;
  } catch (error) {
    status.textContent = error.message || '입력한 주소의 관할을 확인하지 못했습니다.';
  } finally {
    button.disabled = false;
    button.textContent = originalLabel;
  }
}

async function findCurrentAreaCenter(button) {
  const panel = button.closest('.nearest-center-panel');
  const status = panel.querySelector('.route-status');
  const select = panel.querySelector('.nearest-area-select');
  const originalLabel = button.textContent;
  button.disabled = true;
  button.textContent = '현재 위치 확인 중…';
  try {
    const { coords } = await getCurrentPosition();
    const center = window.LifeNaviCenters.trustedNearest(coords, welfareCenters);
    select.value = center.area;
    status.textContent = `직선거리 약 ${center.distance.toFixed(1)}km의 ${center.name}입니다. 관할과 다를 수 있습니다.`;
    button.dataset.fallbackDistance = String(center.distance);
    button.disabled = false;
    button.textContent = `${center.name} 길찾기`;
    await showRoute(button, center.address, coords, center);
  } catch (error) {
    status.textContent = error?.code === 1 ? '현재 위치 사용을 허용하거나 아래에서 센터를 직접 선택해 주세요.' : (error.message || '현재 위치의 센터를 찾지 못했습니다.');
    button.disabled = false;
    button.textContent = originalLabel;
  }
}

async function findAddressNearestCenter(button) {
  const panel = button.closest('.nearest-center-panel');
  const input = panel.querySelector('.nearest-origin-address');
  const status = panel.querySelector('.route-status');
  const select = panel.querySelector('.nearest-area-select');
  const typed = input.value.trim();
  if (!typed) return void (status.textContent = '현재 주소를 입력해 주세요. 동·호수는 입력하지 마세요.');
  const originalLabel = button.textContent;
  button.disabled = true;
  button.textContent = '주소 확인 중…';
  try {
    const data = await resolveTypedAddress(typed);
    const point = {latitude:Number(data.latitude), longitude:Number(data.longitude), accuracy:50, address:data.address || typed};
    const center = window.LifeNaviCenters.trustedNearest(point, welfareCenters);
    select.value = center.area;
    input.value = point.address || typed;
    button.dataset.fallbackDistance = String(center.distance);
    status.textContent = `이 업무를 접수할 수 있는 가장 가까운 곳은 ${center.name}, 직선거리 약 ${center.distance.toFixed(1)}km입니다.`;
    button.disabled = false;
    button.textContent = `${center.name} 길찾기`;
    await showRoute(button, center.address, point, center);
  } catch (error) {
    status.textContent = error.message || '입력 주소 기준 접수처를 찾지 못했습니다.';
  } finally {
    button.disabled = false;
    if (button.textContent === '주소 확인 중…') button.textContent = originalLabel;
  }
}

function escapeHtml(value = '') {
  return String(value).replace(/[&<>'"]/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;',
  })[char]);
}

function openLifeFile(file) {
  textarea.value = file.dataset.text || '';
  textarea.focus();
  document.querySelector('.finder').scrollIntoView({ behavior: 'smooth', block: 'start' });
  form.requestSubmit();
}

document.querySelectorAll('.chip, .citizen-quick').forEach((button) => {
  button.addEventListener('click', () => {
    textarea.value = button.dataset.text || '';
    textarea.focus();
    if (button.classList.contains('citizen-quick')) {
      document.querySelector('.finder').scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' });
      form.requestSubmit();
    }
  });
});

document.querySelectorAll('.life-file').forEach((file) => {
  file.addEventListener('click', () => openLifeFile(file));
  file.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      openLifeFile(file);
    }
  });
});

list.addEventListener('click', (event) => {
  const button = event.target.closest('.detail-btn');
  if (!button) return;
  const service = renderedServicesById.get(String(button.dataset.id));
  if (service) openDetail(service);
});

dialogClose.addEventListener('click', () => dialog.close());
dialog.addEventListener('click', (event) => {
  if (event.target === dialog) dialog.close();
});

detailBody.addEventListener('click', async (event) => {
  if (event.target.closest('.print-detail')) return window.print();
  const destinationChoice = event.target.closest('.destination-choice');
  if (destinationChoice) return showRoute(destinationChoice, destinationChoice.dataset.address || '');

  const routeButton = event.target.closest('.route-btn');
  if (routeButton) return showRoute(routeButton, routeButton.dataset.address || '');

  const welfareButton = event.target.closest('.welfare-route-btn');
  if (welfareButton) {
    const panel = welfareButton.closest('.welfare-center-panel');
    const area = panel.querySelector('.welfare-area-select').value;
    const center = centerForArea(area);
    if (!area) return void (panel.querySelector('.route-status').textContent = '먼저 주소지 관할 읍·면·동을 선택해 주세요.');
    if (!center) return void (panel.querySelector('.route-status').textContent = '선택한 관할 센터 주소를 찾지 못했습니다.');
    return showRoute(welfareButton, center.address, null, center);
  }

  const currentAddressButton = event.target.closest('.current-address-btn');
  if (currentAddressButton) return setCurrentAddress(currentAddressButton);

  const resolveAddressButton = event.target.closest('.resolve-address-btn');
  if (resolveAddressButton) return resolveAddressArea(resolveAddressButton);

  const nearestCenterButton = event.target.closest('.nearest-center-btn');
  if (nearestCenterButton) return findCurrentAreaCenter(nearestCenterButton);

  const nearestAddressButton = event.target.closest('.nearest-address-btn');
  if (nearestAddressButton) return findAddressNearestCenter(nearestAddressButton);

  const nearestAreaButton = event.target.closest('.nearest-area-route-btn');
  if (nearestAreaButton) {
    const panel = nearestAreaButton.closest('.nearest-center-panel');
    const area = panel.querySelector('.nearest-area-select').value;
    const center = centerForArea(area);
    if (!area) return void (panel.querySelector('.route-status').textContent = '방문할 읍·면·동 센터를 먼저 선택해 주세요.');
    if (!center) return void (panel.querySelector('.route-status').textContent = '선택한 센터 주소를 찾지 못했습니다.');
    return showRoute(nearestAreaButton, center.address, null, center);
  }

  const option = event.target.closest('.route-option');
  if (!option) return;
  const panel = option.closest('.visit-panel, .welfare-center-panel');
  const state = panel?._routeState;
  const selected = state?.route.routes?.find((item) => item.key === option.dataset.routeKey);
  if (!selected) return;
  panel.querySelectorAll('.route-option').forEach((item) => item.classList.toggle('is-selected', item === option));
  const route = { ...state.route, ...selected };
  const summary = panel.querySelector('.route-status strong');
  if (summary) summary.textContent = `자동차 약 ${Math.max(1, Math.round(Number(selected.duration_ms) / 60000))}분 · ${(Number(selected.distance_m) / 1000).toFixed(1)}km`;
  renderNaverMap(panel, route, state.origin);
});

detailBody.addEventListener('submit', (event) => {
  const destinationForm = event.target.closest('.destination-form');
  if (!destinationForm) return;
  event.preventDefault();
  const query = String(new FormData(destinationForm).get('destination') || '').trim();
  if (!query) return;
  const area = SearchCore.matchWelfareArea(query, welfareAreas);
  const center = area ? centerForArea(area) : null;
  const destination = center ? center.address : query;
  if (area) destinationForm.querySelector('.area-search').value = area;
  const panel = destinationForm.closest('.visit-panel');
  const button = panel.querySelector('.route-btn');
  button.hidden = false;
  showRoute(button, destination);
});

resetBtn.addEventListener('click', () => {
  searchSequence += 1;
  results.hidden = true;
  renderedServicesById.clear();
  list.innerHTML = '';
  noResult.hidden = true;
  analysisNote.textContent = '';
  if (resultPlan) { resultPlan.hidden = true; resultPlan.innerHTML = ''; }
  submitBtn.disabled = false;
  submitBtn.textContent = '내 파일 만들기 ↗';
  textarea.focus();
  window.scrollTo({ top: 0, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
});

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const query = textarea.value.trim();
  if (!query) return;
  if (query.length > 300) { results.hidden=false; analysisNote.textContent='300자 이내로 입력해 주세요.'; return; }
  if (!baseServices.length) {
    analysisNote.textContent = '공식 생활파일을 불러오는 중입니다. 잠시 후 다시 눌러 주세요.';
    return;
  }

  const requestId = ++searchSequence;
  submitBtn.disabled = true;
  submitBtn.textContent = '찾는 중…';

  try {
    const sensitive = SearchCore.containsSensitiveInfo(query);
    let aiResult = null;
    let publicResult = { services: [], configured: false, note: '' };

    renderServices(localRetrieve(query));
    results.hidden = false;
    analysisNote.textContent = sensitive ? '개인정보로 보이는 값이 있어 외부 전송을 차단했습니다.' : '등록된 생활 파일을 먼저 안내합니다. 추가 서비스를 확인하고 있습니다…';

    if (!sensitive) {
      [aiResult, publicResult] = await Promise.all([aiRetrieve(query), publicDataRetrieve(query)]);
    }
    if (requestId !== searchSequence) return;

    const localFound = SearchCore.mergeUniqueServices(localRetrieve(query), aiResult?.services || []).slice(0, 6);
    const publicFound = Array.isArray(publicResult.services) ? publicResult.services : [];
    const found = SearchCore.mergeUniqueServices(localFound, publicFound).sort((a,b) => SearchCore.actionRank(query,a)-SearchCore.actionRank(query,b)).slice(0, 8);

    if (sensitive) {
      analysisNote.textContent = '개인정보로 보이는 값이 포함되어 외부 AI·공공데이터 전송 없이 기기에 불러온 공식 생활 파일만 검색했습니다. 주민번호·전화번호·이메일·상세주소 등은 지우고 다시 검색해 주세요.';
    } else if (publicFound.length) {
      analysisNote.textContent = `화성시 또는 전국 적용 가능성이 확인된 공공서비스 ${publicFound.length}건을 등록된 공식 생활 파일과 함께 안내합니다.`;
    } else if (localFound.length) {
      analysisNote.textContent = publicResult.note || aiResult?.note || '입력한 문장에서 관련 생활상황을 찾아 등록된 공식 서비스를 안내합니다.';
    } else {
      analysisNote.textContent = publicResult.note || '공공데이터와 등록된 공식 자료에서 관련 서비스를 찾지 못했습니다. 표현을 조금 바꾸어 입력해 주세요.';
    }

    renderServices(found);
    results.hidden = false;
    results.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' });
    document.querySelector('#result-title')?.focus({ preventScroll: true });
  } catch (error) {
    if (requestId !== searchSequence) return;
    renderServices(localRetrieve(query));
    results.hidden = false;
    analysisNote.textContent = `외부 검색 연결이 원활하지 않아 등록된 공식 생활 파일만 검색했습니다. ${error.message || ''}`.trim();
    document.querySelector('#result-title')?.focus({ preventScroll: true });
  } finally {
    if (requestId === searchSequence) {
      submitBtn.disabled = false;
      submitBtn.textContent = '내 파일 만들기 ↗';
    }
  }
});

loadServices().then(() => {
  document.documentElement.dataset.appReady = 'true';
}).catch((error) => {
  document.documentElement.dataset.appReady = 'error';
  analysisNote.textContent = error.message;
  results.hidden = false;
  noResult.hidden = false;
  document.querySelector('#service-status').textContent='기본 자료를 불러오지 못했습니다. 페이지를 새로고침하거나 아래 공식 창구를 이용해 주세요.';
  submitBtn.disabled = true;
  console.error(error);
});
