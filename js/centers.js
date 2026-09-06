'use strict';
window.LifeNaviCenters = (() => {
  function distanceKm(lat, lng, center) {
    const r = v => v * Math.PI / 180;
    const a = Math.sin(r(center.lat-lat)/2)**2 + Math.cos(r(lat))*Math.cos(r(center.lat))*Math.sin(r(center.lng-lng)/2)**2;
    return 6371 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
  }
  function nearest(coords, centers) {
    if (!Number.isFinite(coords.latitude) || !Number.isFinite(coords.longitude) || coords.latitude < 32 || coords.latitude > 40 || coords.longitude < 124 || coords.longitude > 133) return [];
    return centers.filter(c => Number.isFinite(c.lat) && Number.isFinite(c.lng)).map(c => ({...c, distance: distanceKm(coords.latitude, coords.longitude, c)})).sort((a,b) => a.distance-b.distance || a.area.localeCompare(b.area, 'ko')).slice(0,3);
  }
  function link(label, url) {
    const a = document.createElement('a'); a.textContent = label; a.href = url; a.target = '_blank'; a.rel = 'noopener noreferrer'; return a;
  }
  function renderCenter(target, center, heading = '선택한 센터') {
    target.replaceChildren();
    const title = document.createElement('h3'); title.textContent = `${heading} · ${center.name}`;
    const address = document.createElement('p'); address.textContent = center.address;
    const note = document.createElement('p'); note.textContent = center.distance === undefined ? '방문 전 해당 민원의 접수기관과 업무시간을 확인하세요.' : `직선거리 약 ${center.distance.toFixed(1)}km · 가까운 센터는 주소지 관할과 다를 수 있습니다.`;
    const links = document.createElement('div'); links.className='center-links';
    links.append(link('네이버 지도·길찾기 ↗', `https://map.naver.com/p/search/${encodeURIComponent(center.address+' '+center.name)}`));
    if (window.LifeNaviSearch.safeHttpsUrl(center.source_url)) links.append(link('센터 공식 안내 ↗', center.source_url));
    const phone = document.createElement('a'); phone.href='tel:15774200'; phone.textContent='민원안내 1577-4200'; links.append(phone);
    target.append(title,address,note,links);
  }
  async function init(centers, resolveAddress, locate) {
    const select=document.querySelector('#center-area');
    const status=document.querySelector('#center-status');
    const output=document.querySelector('#center-result');
    for (const c of centers) { const option=document.createElement('option'); option.value=c.area; option.textContent=`${c.district} · ${c.area}`; select.append(option); }
    select.addEventListener('change', () => { output.replaceChildren(); const c=centers.find(c=>c.area===select.value); if(c) {renderCenter(output,c); status.textContent='직접 선택한 읍·면·동입니다. 관할을 모르면 주소로 확인하세요.';} });
    document.querySelector('#center-form').addEventListener('submit', async event => {
      event.preventDefault();
      const address=document.querySelector('#center-address').value.trim();
      const button=document.querySelector('#center-find');
      if(!address) return;
      button.disabled=true; output.replaceChildren(); select.value=''; status.textContent='주소지 관할을 확인하고 있습니다…';
      try {
        const explicit=centers.find(c=>address===c.area || address===`화성시 ${c.area}` || address===`화성특례시 ${c.area}`);
        if(explicit) { select.value=explicit.area; renderCenter(output,explicit,'직접 지정한 읍·면·동'); status.textContent='입력한 읍·면·동을 선택했습니다.'; return; }
        const data=await resolveAddress(address);
        const area=window.LifeNaviSearch.matchWelfareArea(data.area||'',centers.map(c=>c.area));
        if(!/화성(?:특례)?시/.test(data.area||'') || !area) throw new Error('화성시 주소지 관할을 확인하지 못했습니다. 읍·면·동을 직접 선택해 주세요.');
        const center=centers.find(c=>c.area===area); select.value=area; renderCenter(output,center,'주소지 관할'); status.textContent='주소의 행정동을 기준으로 확인했습니다.';
      } catch(error) { status.textContent='주소 자동확인을 사용할 수 없습니다. 아래에서 읍·면·동을 직접 선택하거나 민원안내 1577-4200에 문의하세요.'; }
      finally {button.disabled=false;}
    });
    document.querySelector('#center-nearest').addEventListener('click',async event=>{
      const button=event.currentTarget; button.disabled=true; status.textContent='현재 위치를 확인하고 있습니다…'; output.replaceChildren(); select.value='';
      try { const {coords}=await locate(); const list=nearest(coords,centers); if(!list.length) throw new Error(); for(const c of list){const article=document.createElement('article');renderCenter(article,c,'가까운 센터');output.append(article);} status.textContent='현재 위치와 저장된 센터 좌표로 계산했습니다. 주소지 관할 판정은 주소 검색을 이용하세요.'; }
      catch(error){status.textContent=error.code===1?'위치 사용이 거부되었습니다. 주소를 입력하거나 읍·면·동을 직접 선택해 주세요.':'위치를 확인하지 못했습니다. 읍·면·동을 직접 선택해 주세요.';}
      finally {button.disabled=false;}
    });
  }
  return {nearest,renderCenter,init};
})();
