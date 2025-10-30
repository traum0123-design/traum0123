(function(){
  'use strict';
  function qs(id){ return document.getElementById(id); }
  function paramsFromFilters(){
    const p = new URLSearchParams();
    const c = qs('company').value.trim(); if(c) p.set('company_id', c);
    const f = qs('from').value.trim(); if(f) p.set('frm', f);
    const t = qs('to').value.trim(); if(t) p.set('to', t);
    const status = (qs('status').value || 'all').toString();
    if(status === 'closed'){ p.set('only_closed','1'); }
    else { p.set('status', status); p.set('only_closed','0'); }
    if(c && qs('from').value && qs('to').value){ p.set('fill_range','1'); }
    const cur = qs('nextCursor').value.trim(); if(cur) p.set('cursor', cur);
    p.set('limit', '200'); // load more per page
    return p;
  }
  function renderRows(items, append){
    const tb = qs('closingsTable').querySelector('tbody');
    if(!append) tb.innerHTML='';
    if(!items || !items.length){ if(!append) qs('emptyHint').style.display='block'; return; }
    qs('emptyHint').style.display='none';
    items.forEach(it=>{
      const tr = document.createElement('tr');
      const ym = String(it.year) + '-' + String(it.month).padStart(2,'0');
      const status = (it.status||'').toString();
      const chipClass = status==='closed' ? 'status-closed' : (status==='in_progress' ? 'status-progress' : 'status-none');
      tr.innerHTML = `
        <td><input type="checkbox" class="pick" data-company-id="${it.company_id}" data-month="${ym}"></td>
        <td>${it.company_name}</td>
        <td>${ym}</td>
        <td>${it.rows_count||0}</td>
        <td><span class="chip ${chipClass}">${status==='closed'?'마감':(status==='in_progress'?'진행':'미입력')}</span></td>
        <td>${it.updated_at || ''}</td>
      `;
      tb.appendChild(tr);
    });
  }
  let ACC = [];
  function updateSummary(){
    const data = ACC || [];
    const total = data.length;
    let c=0,p=0,n=0; data.forEach(it=>{ const s=(it.status||'').toString(); if(s==='closed') c++; else if(s==='in_progress') p++; else n++; });
    const set = (id,v)=>{ const el = qs(id); if(el) el.textContent = String(v); };
    set('sumTotal', total); set('sumClosed', c); set('sumProgress', p); set('sumNone', n);
  }
  function picks(){ return Array.from(document.querySelectorAll('#closingsTable .pick')); }
  function updateSelection(){
    const sel = picks().filter(b=> b.checked).length;
    const btn = qs('btnExport'); if(btn){ btn.disabled = sel === 0; btn.textContent = sel ? `선택 월 ZIP 다운로드(${sel})` : '선택 월 ZIP 다운로드'; }
  }
  async function load(append){
    const p = paramsFromFilters();
    const res = await fetch('/admin/closings/data.json?' + p.toString(), { credentials: 'same-origin' });
    const j = await res.json();
    if(!res.ok || !j || j.ok===false){ alert(j && j.error ? j.error : '조회 실패'); return; }
    const items = j.items||[];
    if(!append) ACC = items.slice(); else ACC = ACC.concat(items);
    renderRows(items, !!append);
    qs('nextCursor').value = j.next_cursor || '';
    updateSelection();
    updateSummary();
  }
  async function loadAll(){
    // Reset state
    qs('nextCursor').value = '';
    ACC = [];
    let firstPass = true;
    while(true){
      const append = !firstPass;
      firstPass = false;
      const p = paramsFromFilters();
      const res = await fetch('/admin/closings/data.json?' + p.toString(), { credentials: 'same-origin' });
      const j = await res.json();
      if(!res.ok || !j || j.ok===false){ alert(j && j.error ? j.error : '조회 실패'); return; }
      const items = j.items||[];
      ACC = ACC.concat(items);
      renderRows(items, append);
      qs('nextCursor').value = j.next_cursor || '';
      updateSelection();
      updateSummary();
      if(!j.has_more || !j.next_cursor){ break; }
    }
  }
  function buildExportUrl(){
    const rows = Array.from(document.querySelectorAll('#closingsTable .pick:checked'));
    if(!rows.length){ alert('선택된 월이 없습니다.'); return null; }
    const companies = new Set(rows.map(r=> r.dataset.companyId));
    if(companies.size > 1){ alert('서로 다른 회사의 월을 함께 선택할 수 없습니다.'); return null; }
    const companyId = rows[0].dataset.companyId; // 단일 회사만 허용
    const qsParts = rows.map(r=> 'month=' + encodeURIComponent(r.dataset.month));
    return '/admin/closings/export.zip?company_id=' + encodeURIComponent(companyId) + '&' + qsParts.join('&');
  }
  function selectAll(){
    const boxes = document.querySelectorAll('#closingsTable .pick');
    const allChecked = Array.from(boxes).every(b=> b.checked);
    boxes.forEach(b=> b.checked = !allChecked);
    updateSelection();
  }
  function init(){
    const q = qs('btnQuery'); if(q){ q.addEventListener('click', ()=>{
      qs('nextCursor').value='';
      // 회사 미선택(전체)일 때는 전체 불러오기로 한 번에 표시
      if(!qs('company').value.trim()) loadAll(); else load(false);
    }); }
    const more = qs('btnMore'); if(more){ more.addEventListener('click', ()=> load(true)); }
    const all = qs('btnLoadAll'); if(all){ all.addEventListener('click', loadAll); }
    const sel = qs('btnSelectAll'); if(sel){ sel.addEventListener('click', selectAll); }
    const exp = qs('btnExport'); if(exp){ exp.addEventListener('click', ()=>{ const url = buildExportUrl(); if(url) window.location.href = url; }); }
    const table = qs('closingsTable'); if(table){ table.addEventListener('change', (e)=>{ const t = e.target; if(t && t.classList && t.classList.contains('pick')) updateSelection(); }); }
    // 전체 회사 기본: 전체 불러오기
    if(!qs('company').value.trim()) loadAll(); else load(false);
  }
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
