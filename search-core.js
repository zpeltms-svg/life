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

  // 사용자 문장과 등록 서비스 설명에서 같은 생활 개념이 확인될 때만 점수화한다.
  // 짧은 구어체를 서비스 ID에 바로 연결하지 않아 새 서비스나 행정 사실을 만들지 않는다.
  const SEMANTIC_CONCEPTS = [
    ['move', 12, [/(?:이사|이삿짐|전입|새집|새거주지|거주지를옮|주소.*이전)/]],
    ['birth', 11, [/(?:아기|아이|신생아).*(?:태어|낳)|(?:출산|출생)/]],
    ['job', 8, [/(?:취업|구직|일자리|인턴|채용)/]],
    ['startup', 11, [/(?:창업|가게를?열|사업을?시작|사업장)/]],
    ['bulky_waste', 14, [/(?:소파|침대|장롱|책상|냉장고|세탁기|가구).*(?:버리|치우|폐기|처분)|(?:대형폐기물|폐가구|큰쓰레기)/]],
    ['pet', 9, [/(?:반려동물|강아지|고양이|애완동물)/]],
    ['animal_care', 10, [/(?:동물병원|진료비|아프|예방접종|예방주사|백신|광견병|내장칩)/]],
    ['animal_vaccine', 16, [/(?:광견병|내장칩|종합백신)/]],
    ['passport', 14, [/(?:여권)/]],
    ['renewal', 9, [/(?:재발급|갱신|만료|기한이?끝|잃어버|분실)/]],
    ['resident_record', 13, [/(?:주민등록표?|등본|초본|주소이력)/]],
    ['family_certificate', 14, [/(?:가족관계|기본증명서|혼인관계증명서|가족.*증명.*서류)/]],
    ['seal_certificate', 14, [/(?:인감증명|인감서류)/]],
    ['signature_certificate', 14, [/(?:본인서명|서명사실)/]],
    ['marriage', 14, [/(?:혼인신고|결혼.*신고|혼인등록)/]],
    ['death_report', 14, [/(?:사망신고|사망.*등록)/]],
    ['lease_report', 13, [/(?:임대차|전월세|전세|월세).*(?:계약|신고)/]],
    ['fixed_date', 15, [/(?:확정일자)/]],
    ['building_register', 15, [/(?:건축물대장|건물대장)/]],
    ['land_register', 15, [/(?:토지대장|임야대장)/]],
    ['local_tax_certificate', 15, [/(?:지방세|세금).*(?:완납|납세증명|체납없)/]],
    ['vehicle_tax', 15, [/(?:자동차세|차량세금|차세금)/]],
    ['vehicle_registration', 15, [/(?:자동차|차량|차).*(?:등록증)/]],
    ['health_certificate', 15, [/(?:보건증|건강진단결과서)/]],
    ['vaccination', 11, [/(?:예방접종|예방주사|접종병원|위탁의료기관)/]],
    ['water_bill', 15, [/(?:상하수도|수도).*(?:요금|세|납부|자동이체)/]],
    ['kiosk', 15, [/(?:무인민원|무인발급|24시간.*(?:등본|증명서)|주말.*(?:등본|증명서)|야간.*(?:등본|증명서))/]],
    ['complaint', 10, [/(?:국민신문고|고충민원|민원.*(?:넣|접수|신청))/]],
    ['call_center', 12, [/(?:담당부서.*모르|어디에문의|민원.*전화|시청전화|콜센터)/]],
    ['disability_parking', 15, [/(?:장애인).*(?:주차표지|주차증|차량표지|자동차표지)/]],
    ['ev_subsidy', 15, [/(?:전기차|전기자동차).*(?:보조금|지원금|구매지원)/]],
    ['parking_fine', 15, [/(?:주정차|주차).*(?:과태료|단속|위반|의견진술|이의신청)/]],
    ['admin_center', 11, [/(?:주민센터|행정복지센터).*(?:어디|찾|위치|관할)|(?:관할).*(?:주민센터|행정복지센터)/]],
  ];
  const CONTEXT_CONCEPTS = new Set(['renewal', 'animal_care']);

  function semanticConcepts(value = '') {
    const compact = compactText(value);
    const found = new Map();
    for (const [name, weight, patterns] of SEMANTIC_CONCEPTS) {
      if (patterns.some(pattern => pattern.test(compact))) found.set(name, weight);
    }
    return found;
  }

  function serviceSearchText(service) {
    return [service.title, ...(service.intent_groups || []).flat(), ...(service.semantic_phrases || [])].join(' ');
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

    // 상품 추천이나 민간 서류처럼 기존 행정서비스 범위가 아닌 문구는 의미 확장을 하지 않는다.
    const queryConcepts = /(?:취업증명서|사업자등록증|추천|구매|보험|사진관|도장가게|충전소|충전기|배관공사|디자인|투자상담|무엇인가|원리.*궁금|뜻이.*궁금)/.test(compact)
      ? new Map()
      : semanticConcepts(query);
    const serviceConcepts = semanticConcepts(serviceSearchText(service));
    const matchedConcepts = [...queryConcepts].filter(([concept]) => serviceConcepts.has(concept));
    let conceptMatches = 0;
    for (const [concept, weight] of matchedConcepts) {
      // '재발급', '아프다' 같은 문맥어 하나만으로 다른 업무를 추천하지 않는다.
      if (CONTEXT_CONCEPTS.has(concept) && matchedConcepts.length < 2) continue;
      score += weight;
      conceptMatches += 1;
    }
    if (conceptMatches >= 2) score += 10;
    // 사용자가 갱신·분실·만료를 명시했으면 일반 신규 발급 결과를 약하게 만든다.
    if (queryConcepts.has('renewal') && !serviceConcepts.has('renewal')) score -= 12;

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
