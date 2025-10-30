(function(global){
  'use strict';
  function apiBase(){ return document.body ? (document.body.dataset.apiBase || '/api') : '/api'; }
  function setText(id, text, cls){ const el = document.getElementById(id); if(!el) return; el.textContent = text || ''; el.className = (cls||'muted') + ' mt-8'; }
  async function reloadYears(){
    try{
      const res = await fetch(`${apiBase().replace(/\/$/,'')}/admin/api/withholding/years`, { credentials: 'same-origin' });
      const j = await res.json();
      const ul = document.getElementById('yearsList'); if(!ul) return;
      ul.innerHTML = '';
      if(!res.ok || !j || !j.ok || !(j.years||[]).length){
        ul.innerHTML = '<li class="muted">저장된 간이세액표가 없습니다.</li>';
        return;
      }
      (j.years||[]).forEach(item=>{
        const li = document.createElement('li');
        li.textContent = `${item.year}년: ${item.count}건 (${item.min_wage} ~ ${item.max_wage})`;
        ul.appendChild(li);
      });
    }catch(_){ /* ignore */ }
  }
  async function runSample(){
    const y = parseInt(document.getElementById('sYear').value,10)||0;
    const d = parseInt(document.getElementById('sDep').value,10)||0;
    const w = parseInt(document.getElementById('sWage').value,10)||0;
    const out = document.getElementById('sampleOut');
    if(out) out.textContent = '조회 중...';
    try{
      const url = `${apiBase().replace(/\/$/, '')}/admin/tax/withholding/sample?year=${y}&dep=${d}&wage=${w}`;
      const res = await fetch(url, { credentials: 'same-origin' });
      const j = await res.json();
      if(!res.ok || !j.ok){ out && (out.textContent = '오류: ' + (j.error || '조회 실패')); return; }
      if(out){ out.textContent = `소득세: ${Number(j.tax||0).toLocaleString('ko-KR')}원, 지방소득세: ${Number(j.local_tax||0).toLocaleString('ko-KR')}원`; }
    }catch(e){ if(out) out.textContent = '오류: ' + e; }
  }
  async function uploadWithholding(e){
    e.preventDefault();
    const form = e.target;
    if(!form || form.id !== 'withholdingUploadForm') return;
    try{
      setText('uploadMsg','업로드 중...','muted');
      const fd = new FormData(form);
      const res = await fetch(form.action, { method: 'POST', body: fd, credentials: 'same-origin' });
      const j = await res.json().catch(()=>({ ok:false, error:'invalid response'}));
      if(!res.ok || !j || j.ok === false){ setText('uploadMsg', `업로드 실패: ${j && j.error ? j.error : '서버 오류'}`, 'flash error'); return; }
      setText('uploadMsg', `업로드 성공: ${j.year}년 ${j.count}건 반영`, 'flash success');
      reloadYears();
    }catch(err){ setText('uploadMsg', '업로드 실패: ' + (err && err.message ? err.message : err), 'flash error'); }
  }
  document.addEventListener('click', (event)=>{
    const btn = event.target.closest('[data-action="runWithholdingSample"]');
    if(!btn) return;
    event.preventDefault();
    runSample();
  });
  document.addEventListener('submit', (e)=>{
    const form = e.target && e.target.closest ? e.target.closest('#withholdingUploadForm') : null;
    if(!form) return;
    uploadWithholding(e);
  }, true);
  global.runWithholdingSample = runSample;
})(window);
