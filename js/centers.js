'use strict';
window.LifeNaviCenters = (() => {
  const MAX_LOCATION_ACCURACY_METERS = 2000;
  const MAX_NEAREST_DISTANCE_KM = 12;
  const VERIFIED_ROAD_AREAS = Object.freeze([
    { road: '상신하길로', area: '향남읍' },
  ]);

  function distanceKm(lat, lng, center) {
    const r = value => value * Math.PI / 180;
    const a = Math.sin(r(center.lat-lat)/2)**2 + Math.cos(r(lat))*Math.cos(r(center.lat))*Math.sin(r(center.lng-lng)/2)**2;
    return 6371 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
  }

  function nearest(coords, centers, limit = 1) {
    if (!Number.isFinite(coords?.latitude) || !Number.isFinite(coords?.longitude) || coords.latitude < 32 || coords.latitude > 40 || coords.longitude < 124 || coords.longitude > 133) return [];
    return centers
      .filter(center => Number.isFinite(center.lat) && Number.isFinite(center.lng))
      .map(center => ({...center, distance: distanceKm(coords.latitude, coords.longitude, center)}))
      .sort((a,b) => a.distance-b.distance || a.area.localeCompare(b.area, 'ko'))
      .slice(0, Math.max(1, Math.min(3, Number(limit) || 1)));
  }

  function knownJurisdiction(address, centers) {
    const normalized = String(address || '').normalize('NFKC').replace(/\s+/g, ' ').trim();
    if (!normalized) return null;
    const explicit = centers.find(center => normalized === center.area || normalized === '화성시 ' + center.area || normalized === '화성특례시 ' + center.area);
    if (explicit) return explicit;
    const rule = VERIFIED_ROAD_AREAS.find(item => new RegExp('(?:^|\\s)' + item.road + '(?:\\d+번길)?(?:\\s|\\d|$)').test(normalized));
    return rule ? centers.find(center => center.area === rule.area) || null : null;
  }

  function trustedNearest(coords, centers) {
    const accuracy = Number(coords?.accuracy);
    if (!Number.isFinite(accuracy) || accuracy <= 0 || accuracy > MAX_LOCATION_ACCURACY_METERS) {
      const error = new Error('현재 위치의 정확도가 낮습니다. 상신하길로 274처럼 주소를 입력해 관할센터를 확인해 주세요.');
      error.code = 'LOCATION_INACCURATE';
      throw error;
    }
    const center = nearest(coords, centers, 1)[0];
    if (!center) {
      const error = new Error('현재 위치 좌표를 확인하지 못했습니다. 주소를 입력해 주세요.');
      error.code = 'LOCATION_INVALID';
      throw error;
    }
    if (center.distance > MAX_NEAREST_DISTANCE_KM) {
      const error = new Error('받은 현재 위치가 화성시 생활권과 너무 멉니다. 기기 위치를 다시 확인하거나 주소를 입력해 주세요.');
      error.code = 'LOCATION_OUTSIDE_COVERAGE';
      throw error;
    }
    return {...center, locationAccuracy: accuracy};
  }

  function link(label, url) {
    const anchor = document.createElement('a'); anchor.textContent = label; anchor.href = url; anchor.target = '_blank'; anchor.rel = 'noopener noreferrer'; return anchor;
  }

  function renderCenter(target, center, heading = '선택한 센터') {
    target.replaceChildren();
    const title = document.createElement('h3'); title.textContent = heading + ' · ' + center.name;
    const address = document.createElement('p'); address.textContent = center.address;
    const note = document.createElement('p'); note.textContent = center.distance === undefined ? '방문 전 해당 민원의 접수기관과 업무시간을 확인하세요.' : '직선거리 약 ' + center.distance.toFixed(1) + 'km · 현재 위치 기준이며 주소지 관할과 다를 수 있습니다.';
    const links = document.createElement('div'); links.className='center-links';
    links.append(link('네이버 지도·길찾기 ↗', 'https://map.naver.com/p/search/' + encodeURIComponent(center.address+' '+center.name)));
    if (window.LifeNaviSearch.safeHttpsUrl(center.source_url)) links.append(link('센터 공식 안내 ↗', center.source_url));
    const phone = document.createElement('a'); phone.href='tel:15774200'; phone.textContent='민원안내 1577-4200'; links.append(phone);
    target.append(title,address,note,links);
  }

  async function init(centers, resolveAddress, locate) {
    const select=document.querySelector('#center-area');
    const status=document.querySelector('#center-status');
    const output=document.querySelector('#center-result');
    for (const center of centers) { const option=document.createElement('option'); option.value=center.area; option.textContent=center.district + ' · ' + center.area; select.append(option); }
    select.addEventListener('change', () => { output.replaceChildren(); const center=centers.find(item=>item.area===select.value); if(center) {renderCenter(output,center); status.textContent='직접 선택한 읍·면·동입니다. 관할을 모르면 주소로 확인하세요.';} });
    document.querySelector('#center-form').addEventListener('submit', async event => {
      event.preventDefault();
      const address=document.querySelector('#center-address').value.trim();
      const button=document.querySelector('#center-find');
      if(!address) return;
      button.disabled=true; output.replaceChildren(); select.value=''; status.textContent='주소지 관할을 확인하고 있습니다…';
      try {
        const local = knownJurisdiction(address, centers);
        if(local) { select.value=local.area; renderCenter(output,local,'주소지 관할'); status.textContent='검증된 주소 자료에 따라 ' + local.area + ' 관할로 확인했습니다.'; return; }
        const data=await resolveAddress(address);
        const area=window.LifeNaviSearch.matchWelfareArea(data.area||'',centers.map(center=>center.area));
        if(!/화성(?:특례)?시/.test(data.area||'') || !area) throw new Error('화성시 주소지 관할을 확인하지 못했습니다. 읍·면·동을 직접 선택해 주세요.');
        const center=centers.find(item=>item.area===area); select.value=area; renderCenter(output,center,'주소지 관할'); status.textContent='주소의 행정동을 기준으로 확인했습니다.';
      } catch(error) { status.textContent=error.message || '주소 자동확인을 사용할 수 없습니다. 아래에서 읍·면·동을 직접 선택하거나 민원안내 1577-4200에 문의하세요.'; }
      finally {button.disabled=false;}
    });
    document.querySelector('#center-nearest').addEventListener('click',async event=>{
      const button=event.currentTarget; button.disabled=true; status.textContent='정확한 현재 위치를 확인하고 있습니다…'; output.replaceChildren(); select.value='';
      try {
        const {coords}=await locate();
        const center=trustedNearest(coords,centers);
        renderCenter(output,center,'현재 위치에서 가장 가까운 센터');
        status.textContent='기기 위치 정확도 약 ±' + Math.round(center.locationAccuracy) + 'm로 계산했습니다. 이 결과는 주소지 관할 판정이 아닙니다.';
      } catch(error) {
        status.textContent=error.code===1?'위치 사용이 거부되었습니다. 주소를 입력하거나 읍·면·동을 직접 선택해 주세요.':(error.message || '위치를 확인하지 못했습니다. 주소를 입력해 주세요.');
      } finally {button.disabled=false;}
    });
  }

  return {nearest,trustedNearest,knownJurisdiction,renderCenter,init};
})();
