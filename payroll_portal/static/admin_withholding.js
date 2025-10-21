(function(global){
  'use strict';
  async function runSample(){
    const y = parseInt(document.getElementById('sYear').value,10)||0;
    const d = parseInt(document.getElementById('sDep').value,10)||0;
    const w = parseInt(document.getElementById('sWage').value,10)||0;
    const out = document.getElementById('sampleOut');
    if(out) out.textContent = '조회 중...';
    try{
      const base = document.body ? (document.body.dataset.apiBase || '/api') : '/api';
      const url = `${base.replace(/\/$/, '')}/admin/withholding/sample?year=${y}&dep=${d}&wage=${w}`;
      const res = await fetch(url);
      const j = await res.json();
      if(!res.ok || !j.ok){ out && (out.textContent = '오류: ' + (j.error || '조회 실패')); return; }
      if(out){ out.textContent = `소득세: ${Number(j.tax||0).toLocaleString('ko-KR')}원, 지방소득세: ${Number(j.local_tax||0).toLocaleString('ko-KR')}원`; }
    }catch(e){ if(out) out.textContent = '오류: ' + e; }
  }
  global.runWithholdingSample = runSample;
})(window);
