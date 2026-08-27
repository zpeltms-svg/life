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
  document.querySelector('#detail-body').innerHTML = `
    <p>${escapeHtml(service.summary)}</p>
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
