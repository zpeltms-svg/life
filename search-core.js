(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.LifeNaviSearch = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const SENSITIVE_PATTERNS = [
    /(?<!\d)(?:\d[ -]?){11,19}(?!\d)/g, // 카드·계좌번호 형태
    /\b\d{6}\s*[- ]?\s*[1-8]\d{6}\b/g, // 주민·외국인등록번호 형태
    /\b01[016789]\s*[- ]?\s*\d{3,4}\s*[- ]?\s*\d{4}\b/g, // 휴대전화
    /\b0(?:2|3[1-3]|4[1-4]|5[1-5]|6[1-4]|70|50\d)\s*[- ]?\s*\d{3,4}\s*[- ]?\s*\d{4}\b/g, // 국내 유선·인터넷·안심전화
    /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi, // 이메일
    /\b\d{3}\s*[- ]?\s*\d{2}\s*[- ]?\s*\d{5}\b/g, // 사업자등록번호
    /[가-힣A-Za-z0-9·.()-]{1,30}(?:대로|로|길)\s*\d{1,5}(?:-\d{1,5})?(?:\s*\d{1,4}동)?/g, // 상세 도로명주소 형태
    /[가-힣A-Za-z0-9·.()-]{1,20}(?:읍|면|동|리)\s+\d{1,5}(?:-\d{1,5})?\b/g, // 지번주소 형태
  ];

  function normalizeText(value = '') {
    return String(value)
      .normalize('NFKC')
      .toLowerCase()
      .replace(/[.,!?;:()[\]{}"'`~@#$%^&*_+=|\\/<>]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function compactText(value = '') {
    return normalizeText(value).replace(/\s+/g, '');
  }

  function containsSensitiveInfo(value = '') {
    const text = String(value).normalize('NFKC').replace(/[\u200b-\u200f\u2060\ufeff]/g, '').replace(/[\u2010-\u2015\u2212]/g, '-');
    return SENSITIVE_PATTERNS.some((pattern) => {
      pattern.lastIndex = 0;
      return pattern.test(text);
    });
  }

  function keywordWeight(keyword) {
    const size = compactText(keyword).length;
    if (size >= 6) return 8;
    if (size >= 4) return 6;
    if (size >= 3) return 4;
    if (size >= 2) return 4;
    return 3;
  }

  function scoreService(query, service) {
    const normalized = normalizeText(query);
    const compact = compactText(query);
    if (!normalized) return 0;
    if (isExcluded(query, service)) return 0;

    let score = 0;
    for (const group of service.intent_groups || []) {
      if (group.every(word => compact.includes(compactText(word)))) score += 8;
    }
    const title = normalizeText(service.title || '');
    const titleCompact = compactText(service.title || '');

    if (title && normalized.includes(title)) score += 14;
    if (titleCompact && compact.includes(titleCompact)) score += 14;

    const seen = new Set();
    for (const rawKeyword of service.keywords || []) {
      const keyword = normalizeText(rawKeyword);
      const keywordCompact = compactText(rawKeyword);
      if (!keyword || seen.has(keywordCompact)) continue;
      seen.add(keywordCompact);
      if (normalized.includes(keyword) || compact.includes(keywordCompact)) {
        score += keywordWeight(rawKeyword);
      }
    }

    for (const rawNegative of service.negative_keywords || []) {
      const negative = normalizeText(rawNegative);
      const negativeCompact = compactText(rawNegative);
      if (negative && (normalized.includes(negative) || compact.includes(negativeCompact))) score -= 12;
    }

    // 제목의 핵심 토큰 일치도도 보조 점수로 사용하되 한 글자는 무시합니다.
    for (const token of title.split(' ')) {
      if (token.length >= 2 && normalized.includes(token)) score += 2;
    }

    return score;
  }

  function localRetrieve(query, services, limit = 6) {
    if (!Array.isArray(services) || !normalizeText(query)) return [];
    return services
      .map((service) => ({ service, score: scoreService(query, service) }))
      .filter((item) => item.score >= 4)
      .sort((a, b) => actionRank(query, a.service) - actionRank(query, b.service) || b.score - a.score || (a.service.priority ?? 99) - (b.service.priority ?? 99) || String(a.service.id || '').localeCompare(String(b.service.id || ''), 'ko'))
      .slice(0, limit)
      .map((item) => item.service);
  }

  function mergeUniqueServices(...groups) {
    const merged = new Map();
    for (const service of groups.flat()) {
      if (service && service.id && !merged.has(service.id)) merged.set(service.id, service);
    }
    return [...merged.values()];
  }

  function matchWelfareArea(value, areas) {
    const compact = compactText(value);
    if (!compact || !Array.isArray(areas)) return '';
    if (/(?:수원|용인|오산|평택|안산|시흥|서울|부산|인천|대전|대구|광주|울산)(?:시|특별시|광역시)/.test(compact)) return '';

    // 완전 포함을 우선하여 '동탄1동'과 '동탄10동' 같은 오판을 줄입니다.
    const bySpecificity = [...areas].sort((a, b) => compactText(b).length - compactText(a).length || String(a).localeCompare(String(b), 'ko'));
    const exactContained = bySpecificity.find((area) => compact.includes(compactText(area)));
    if (exactContained) return exactContained;

    // 사용자가 읍·면·동 일부만 검색하는 경우 고유하게 일치할 때만 자동 선택합니다.
    const partial = areas.filter((area) => {
      const candidate = compactText(area);
      return candidate.startsWith(compact) || candidate.includes(compact);
    });
    return partial.length === 1 ? partial[0] : '';
  }


  function safeHttpsUrl(value = '', fallback = '') {
    try {
      const parsed = new URL(String(value || '').trim());
      if (parsed.protocol === 'https:' && parsed.hostname && !parsed.username && !parsed.password) return parsed.href;
    } catch (_) {
      // invalid URL
    }
    return fallback;
  }

  function isExcluded(query, service) {
    const q = compactText(query);
    return (service.exclude_keywords || []).some(word => q.includes(compactText(word)));
  }

  function actionRank(query, service) {
    const birth = /(?:아기|아이|자녀).*(?:태어|낳)|출산했|출생신고/.test(compactText(query));
    if (birth) {
      const order = ['BIRTH-001', 'BIRTH-002', 'BIRTH-003', 'BIRTH-004', 'BIRTH-005'];
      const index = order.indexOf(service.id);
      if (index >= 0) return index;
    }
    return 10;
  }

  function sourceAgeDays(dateString, nowMs = Date.now()) {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(dateString || '').trim());
    if (!match) return Number.POSITIVE_INFINITY;
    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);
    const checked = Date.UTC(year, month - 1, day);
    const parsed = new Date(checked);
    if (!Number.isFinite(checked) || parsed.getUTCFullYear() !== year || parsed.getUTCMonth() !== month - 1 || parsed.getUTCDate() !== day) return Number.POSITIVE_INFINITY;
    if (checked > Number(nowMs) + 86400000) return Number.POSITIVE_INFINITY;
    return Math.max(0, Math.floor((Number(nowMs) - checked) / 86400000));
  }

  return {
    normalizeText,
    compactText,
    containsSensitiveInfo,
    scoreService,
    localRetrieve,
    mergeUniqueServices,
    matchWelfareArea,
    safeHttpsUrl,
    sourceAgeDays,
    isExcluded,
    actionRank,
  };
});
