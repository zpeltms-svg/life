const form = document.querySelector('#guide-form');
const textarea = document.querySelector('#situation');
const submitBtn = document.querySelector('#submit-btn');
const results = document.querySelector('#results');
const list = document.querySelector('#result-list');
const noResult = document.querySelector('#no-result');
const analysisNote = document.querySelector('#analysis-note');
const resetBtn = document.querySelector('#reset-btn');
const dialog = document.querySelector('#detail-dialog');
const dialogClose = document.querySelector('#detail-close');

let serviceData = [];

async function loadServices() {
  const response = await fetch('./data/services.json', { cache: 'no-store' });
  if (!response.ok) throw new Error('행정서비스 자료를 불러오지 못했습니다.');
  const data = await response.json();
  serviceData = data.services || [];
}

function localRetrieve(query) {
  const normalized = query.toLowerCase().replace(/\s+/g, ' ');
  const scored = serviceData.map((service) => {
    let score = 0;
    for (const keyword of service.keywords || []) {
      if (normalized.includes(keyword.toLowerCase())) score += keyword.length >= 4 ? 3 : 2;
    }
    if (normalized.includes(service.category_label.toLowerCase())) score += 3;
    return { service, score };
  });

  const best = Math.max(...scored.map((item) => item.score), 0);
  if (best === 0) return [];

  const matchingCategories = new Set(
    scored.filter((item) => item.score > 0).map((item) => item.service.category)
  );

  return serviceData
    .filter((service) => matchingCategories.has(service.category))
    .sort((a, b) => a.priority - b.priority)
    .slice(0, 6);
}

async function aiRetrieve(query) {
  try {
    const response = await fetch('/api/guide', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query })
    });
    if (!response.ok) throw new Error('AI API not available');
    const data = await response.json();
    if (!Array.isArray(data.service_ids)) throw new Error('Invalid AI response');
    const found = data.service_ids.map((id) => serviceData.find((s) => s.id === id)).filter(Boolean);
    return { services: found, note: data.note || '입력한 상황을 바탕으로 관련 서비스를 찾았습니다.' };
  } catch (_) {
    return null;
  }
}

function renderServices(servicesToRender) {
  list.innerHTML = '';
  noResult.hidden = servicesToRender.length > 0;
  servicesToRender.forEach((service, index) => {
    const card = document.createElement('article');
    card.className = 'service-card';
    card.innerHTML = `
      <div>
        <span class="badge">${escapeHtml(service.category_label)}</span>
        <h3>${index + 1}. ${escapeHtml(service.title)}</h3>
        <p>${escapeHtml(service.summary)}</p>
        ${service.online_application ? `<a class="online-link" href="${escapeHtml(service.online_application.url)}" target="_blank" rel="noopener noreferrer">● 온라인 신청 가능 <span>${escapeHtml(service.online_application.label)} ↗</span></a>` : ''}
        <div class="meta-row">
          <span><strong>처리기관</strong> ${escapeHtml(service.office)}</span>
          <span><strong>최근 자료확인</strong> ${escapeHtml(service.source_checked)}</span>
        </div>
      </div>
      <button class="detail-btn" type="button" data-id="${service.id}">자세히 보기 →</button>
    `;
    list.appendChild(card);
  });
}

function openDetail(service) {
  document.querySelector('#detail-category').textContent = service.category_label;
  document.querySelector('#detail-title').textContent = service.title;
  const method = (service.method || []).map((x) => `<li>${escapeHtml(x)}</li>`).join('');
  const documents = (service.documents || []).map((x) => `<li>${escapeHtml(x)}</li>`).join('');
  const online = service.online_application ? `
    <section class="application-panel online-panel">
      <p>ONLINE APPLICATION</p>
      <strong>온라인 신청이 가능합니다.</strong>
      <a href="${escapeHtml(service.online_application.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(service.online_application.label)} <span>↗</span></a>
    </section>` : '';
  const visit = service.visit_destination ? `
    <section class="application-panel visit-panel" data-service-id="${escapeHtml(service.id)}">
      <p>OFFLINE VISIT</p>
      <strong>${escapeHtml(service.visit_destination.name)}</strong>
      <span>${escapeHtml(service.visit_destination.address)}</span>
      <button class="route-btn" type="button">현재 위치에서 예상시간 보기</button>
      <form class="destination-form">
        <label>다른 장소로 길찾기<input name="destination" maxlength="120" placeholder="주소를 입력하세요 (예: 화성시 동탄대로 635)" autocomplete="street-address"></label>
        <button type="submit">이 주소 검색</button>
      </form>
      <p class="route-helper">주소를 검색하면 현재 위치에서 출발하는 자동차 경로를 지도에 표시합니다.</p>
      <p class="route-status" aria-live="polite"></p>
    </section>` : service.offline_notice ? `<section class="application-panel jurisdiction-panel"><p>OFFLINE VISIT</p><strong>방문 신청 전 관할 확인이 필요합니다.</strong><span>${escapeHtml(service.offline_notice)}</span></section>` : '';
  document.querySelector('#detail-body').innerHTML = `
    <p>${escapeHtml(service.summary)}</p>
    <div class="application-actions">${online}${visit}</div>
    <dl class="detail-grid">
      <dt>대상</dt><dd>${escapeHtml(service.who)}</dd>
      <dt>언제</dt><dd>${escapeHtml(service.when)}</dd>
      <dt>신청방법</dt><dd><ul>${method}</ul></dd>
      <dt>준비사항</dt><dd><ul>${documents}</ul></dd>
      <dt>처리기관</dt><dd>${escapeHtml(service.office)}</dd>
      <dt>처리기간</dt><dd>${escapeHtml(service.processing_time)}</dd>
    </dl>
    <div class="source-box">
      <strong>근거자료</strong>
      <p>${escapeHtml(service.source_name)}</p>
      <p><a href="${service.source_url}" target="_blank" rel="noopener noreferrer">공식 원문 열기</a></p>
      <small>자료 확인일: ${escapeHtml(service.source_checked)} · 실제 신청 전 최신 내용을 다시 확인하세요.</small>
    </div>
  `;
  dialog.showModal();
}

async function showRoute(button, destinationQuery = '') {
  const panel = button.closest('.visit-panel');
  const status = panel.querySelector('.route-status');
  if (!navigator.geolocation) {
    status.textContent = '이 브라우저에서는 현재 위치를 지원하지 않습니다.';
    return;
  }
  button.disabled = true;
  button.textContent = '현재 위치 확인 중…';
  navigator.geolocation.getCurrentPosition(async ({ coords }) => {
    try {
      const response = await fetch('/api/route', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ service_id: panel.dataset.serviceId, destination_query: destinationQuery, origin: { latitude: coords.latitude, longitude: coords.longitude } })
      });
      const route = await response.json();
      if (!response.ok) throw new Error(route.error);
      const minutes = Math.max(1, Math.round(route.duration_ms / 60000));
      const kilometers = (route.distance_m / 1000).toFixed(1);
      panel._routeState = { route, origin: coords };
      status.innerHTML = `<strong>자동차 약 ${minutes}분 · ${kilometers}km</strong><a href="nmap://route/car?slat=${coords.latitude}&slng=${coords.longitude}&sname=현재 위치&dlat=${route.latitude}&dlng=${route.longitude}&dname=${encodeURIComponent(route.destination)}&appname=com.hwaseong.life" rel="noopener noreferrer">네이버 지도로 길 안내 ↗</a>`;
      await renderNaverMap(panel, route, coords);
      if (Array.isArray(route.routes) && route.routes.length > 1) {
        const options = route.routes.map((item, index) => {
          const optionMinutes = Math.max(1, Math.round(item.duration_ms / 60000));
          const optionKilometers = (item.distance_m / 1000).toFixed(1);
          return `<button class="route-option${index === 0 ? ' is-selected' : ''}" type="button" data-route-key="${item.key}"><b>${item.label}</b><span>약 ${optionMinutes}분 · ${optionKilometers}km</span></button>`;
        }).join('');
        status.insertAdjacentHTML('beforeend', `<div class="route-options" aria-label="경로 선택">${options}</div>`);
      }
      button.hidden = true;
    } catch (error) {
      status.textContent = error.message || '경로 정보를 불러오지 못했습니다.';
      button.disabled = false;
      button.textContent = '현재 위치에서 예상시간 보기';
    }
  }, () => {
    status.textContent = '예상시간을 보려면 현재 위치 사용을 허용해 주세요.';
    button.disabled = false;
    button.textContent = '현재 위치에서 예상시간 보기';
  }, { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 });
}

function loadNaverMaps(clientId) {
  if (window.naver?.maps) return Promise.resolve();
  const existing = document.querySelector('#naver-maps-sdk');
  if (existing) return new Promise((resolve, reject) => {
    existing.addEventListener('load', resolve, { once: true });
    existing.addEventListener('error', reject, { once: true });
  });
  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.id = 'naver-maps-sdk';
    script.src = `https://oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=${encodeURIComponent(clientId)}`;
    script.onload = resolve;
    script.onerror = reject;
    document.head.appendChild(script);
  });
}

async function renderNaverMap(panel, route, origin) {
  if (!route.map_client_id || !Array.isArray(route.path) || !route.path.length) return;
  try {
    await loadNaverMaps(route.map_client_id);
    const oldMap = panel.querySelector('.naver-route-map');
    if (oldMap) oldMap.remove();
    const mapElement = document.createElement('div');
    mapElement.className = 'naver-route-map';
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
    // 지도 SDK가 허용 도메인 또는 설정 문제로 로드되지 않아도 길 안내 링크는 유지합니다.
  }
}

function escapeHtml(value = '') {
  return String(value).replace(/[&<>'"]/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  })[char]);
}

document.querySelectorAll('.chip').forEach((button) => {
  button.addEventListener('click', () => {
    textarea.value = button.dataset.text || '';
    textarea.focus();
  });
});

function openLifeFile(file) {
  textarea.value = file.dataset.text || '';
  textarea.focus();
  document.querySelector('.finder').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

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
  const service = serviceData.find((item) => item.id === button.dataset.id);
  if (service) openDetail(service);
});

dialogClose.addEventListener('click', () => dialog.close());
dialog.addEventListener('click', (event) => {
  if (event.target === dialog) dialog.close();
});

document.querySelector('#detail-body').addEventListener('click', (event) => {
  const button = event.target.closest('.route-btn');
  if (button) showRoute(button);

  const option = event.target.closest('.route-option');
  if (!option) return;
  const panel = option.closest('.visit-panel');
  const state = panel?._routeState;
  const selected = state?.route.routes?.find((item) => item.key === option.dataset.routeKey);
  if (!selected) return;
  panel.querySelectorAll('.route-option').forEach((item) => item.classList.toggle('is-selected', item === option));
  const route = { ...state.route, ...selected };
  const summary = panel.querySelector('.route-status strong');
  if (summary) summary.textContent = `자동차 약 ${Math.max(1, Math.round(selected.duration_ms / 60000))}분 · ${(selected.distance_m / 1000).toFixed(1)}km`;
  renderNaverMap(panel, route, state.origin);
});

document.querySelector('#detail-body').addEventListener('submit', (event) => {
  const form = event.target.closest('.destination-form');
  if (!form) return;
  event.preventDefault();
  const query = new FormData(form).get('destination')?.trim();
  if (!query) return;
  const panel = form.closest('.visit-panel');
  const button = panel.querySelector('.route-btn');
  button.hidden = false;
  showRoute(button, query);
});

resetBtn.addEventListener('click', () => {
  results.hidden = true;
  textarea.focus();
  window.scrollTo({ top: 0, behavior: 'smooth' });
});

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const query = textarea.value.trim();
  if (!query) return;

  submitBtn.disabled = true;
  submitBtn.textContent = '찾는 중…';

  const aiResult = await aiRetrieve(query);
  let found;
  if (aiResult && aiResult.services.length) {
    found = aiResult.services;
    analysisNote.textContent = aiResult.note;
  } else {
    found = localRetrieve(query);
    analysisNote.textContent = found.length
      ? '입력한 문장에서 관련 생활상황을 찾아 공식자료에 등록된 서비스를 우선 안내합니다.'
      : '등록된 자료 범위에서 관련 서비스를 찾지 못했습니다.';
  }

  renderServices(found);
  results.hidden = false;
  results.scrollIntoView({ behavior: 'smooth', block: 'start' });
  submitBtn.disabled = false;
  submitBtn.textContent = '확인하기';
});

loadServices().catch((error) => {
  analysisNote.textContent = error.message;
  console.error(error);
});
