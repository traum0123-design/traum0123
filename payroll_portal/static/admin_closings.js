(function(){
  'use strict';
  function qs(id){ return document.getElementById(id); }
  function paramsFromFilters(){
    const p = new URLSearchParams();
    const c = qs('company').value.trim(); if(c) p.set('company_id', c);
    const f = qs('from').value.trim(); if(f) p.set('frm', f);
    const t = qs('to').value.trim(); if(t) p.set('to', t);
    const oc = qs('onlyClosed').checked; if(oc) p.set('only_closed', '1'); else p.set('only_closed','0');
    const cur = qs('nextCursor').value.trim(); if(cur) p.set('cursor', cur);
    p.set('limit', '50');
    return p;
  }
  function renderRows(items){
    const tb = qs('closingsTable').querySelector('tbody'); tb.innerHTML='';
    if(!items || !items.length){ qs('emptyHint').style.display='block'; return; }
    qs('emptyHint').style.display='none';
    items.forEach(it=>{
      const tr = document.createElement('tr');
      const ym = String(it.year) + '-' + String(it.month).padStart(2,'0');
      tr.innerHTML = `
        <td><input type="checkbox" class="pick" data-company-id="${it.company_id}" data-month="${ym}"></td>
        <td>${it.company_name}</td>
        <td>${ym}</td>
        <td>${it.rows_count||0}</td>
        <td>${it.is_closed? '마감':'진행'}</td>
        <td>${it.updated_at || ''}</td>
      `;
      tb.appendChild(tr);
    });
  }
  async function load(){
    const p = paramsFromFilters();
    const res = await fetch('/admin/closings/data.json?' + p.toString(), { credentials: 'same-origin' });
    const j = await res.json();
    if(!res.ok || !j || j.ok===false){ alert(j && j.error ? j.error : '조회 실패'); return; }
    renderRows(j.items||[]);
    qs('nextCursor').value = j.next_cursor || '';
  }
  function buildExportUrl(){
    const rows = Array.from(document.querySelectorAll('#closingsTable .pick:checked'));
    if(!rows.length){ alert('선택된 월이 없습니다.'); return null; }
    const companyId = rows[0].dataset.companyId; // 한 회사 기준
    const qsParts = rows.map(r=> 'month=' + encodeURIComponent(r.dataset.month));
    return '/admin/closings/export.zip?company_id=' + encodeURIComponent(companyId) + '&' + qsParts.join('&');
  }
  function selectAll(){
    const boxes = document.querySelectorAll('#closingsTable .pick');
    const allChecked = Array.from(boxes).every(b=> b.checked);
    boxes.forEach(b=> b.checked = !allChecked);
  }
  function init(){
    const q = qs('btnQuery'); if(q){ q.addEventListener('click', ()=>{ qs('nextCursor').value=''; load(); }); }
    const more = qs('btnMore'); if(more){ more.addEventListener('click', load); }
    const sel = qs('btnSelectAll'); if(sel){ sel.addEventListener('click', selectAll); }
    const exp = qs('btnExport'); if(exp){ exp.addEventListener('click', ()=>{ const url = buildExportUrl(); if(url) window.location.href = url; }); }
    load();
  }
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();

