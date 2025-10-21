(function(global){
  'use strict';
  function qs(sel){ return document.querySelector(sel); }
  function qsa(sel){ return Array.prototype.slice.call(document.querySelectorAll(sel)); }

  // 계산방법 UI
  function openCalcConfig(){ buildCalcConfig(); var m=qs('#calcConfigModal'); if(m) m.style.display='flex'; }
  function closeCalcConfig(){ var m=qs('#calcConfigModal'); if(m) m.style.display='none'; }
  function buildCalcConfig(){
    var body = qs('#calcConfigBody'); if(!body) return; body.innerHTML='';
    var classify = global.classify; var loadInsIncludeMap = (global.PayrollState && global.PayrollState.loadInsIncludeMap) || function(){ return { nps:{}, nhis:{}, ei:{} }; };
    var data = classify(); var inc = loadInsIncludeMap();
    var q = (qs('#calcSearch') && qs('#calcSearch').value || '').trim().toLowerCase();
    (data.earnings||[]).forEach(function(t){ var field=t[0], label=t[1]; var name=String(label||''); if(q && name.toLowerCase().indexOf(q)===-1) return;
      var nhChecked = (inc.nhis && Object.keys(inc.nhis).length>0) ? !!inc.nhis[field] : (label==='기본급' || field==='기본급');
      var eiChecked = (inc.ei && Object.keys(inc.ei).length>0) ? !!inc.ei[field] : (label==='기본급' || field==='기본급');
      var tr = document.createElement('tr');
      tr.innerHTML = '<td class="col-name">'+label+'</td>'+
        '<td class="radio-cell"><label class="radio-wrap"><input class="as-radio" type="checkbox" data-ins="nhis" data-field="'+field+'" '+(nhChecked?'checked':'')+'></label></td>'+
        '<td class="radio-cell"><label class="radio-wrap"><input class="as-radio" type="checkbox" data-ins="ei" data-field="'+field+'" '+(eiChecked?'checked':'')+'></label></td>'+
        '<td class="col-type muted" title="사원별 \'기준보수월액\'으로 계산됩니다.">필드값 사용</td>';
      body.appendChild(tr);
    });
  }
  function applyCalcConfigImmediate(){
    var inc = { nps:{}, nhis:{}, ei:{} };
    qsa('#calcConfigBody input[type="checkbox"]').forEach(function(cb){ var ins=cb.dataset.ins, f=cb.dataset.field; if(cb.checked){ inc[ins][f]=true; } });
    if(global.PayrollState && PayrollState.saveInsIncludeMap) PayrollState.saveInsIncludeMap(inc);
    // 서버 저장
    try{ fetch('/api/portal/'+encodeURIComponent(global.SLUG)+'/fields/calc-config', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ include: { nhis: inc.nhis, ei: inc.ei } }) }); }catch(_){ }
    try{ if(global.computeAll) global.computeAll(); }catch(_){ }
  }
  function saveCalcConfig(){
    try{ applyCalcConfigImmediate(); }catch(_){ }
    closeCalcConfig();
    if(global.PayrollFlash) global.PayrollFlash('success', '계산방법이 저장되었습니다.');
  }
  function wireCalcConfigListeners(){
    document.addEventListener('input', function(e){ if(e.target && e.target.id==='calcSearch'){ buildCalcConfig(); } });
    document.addEventListener('click', function(e){ var id=(e.target&&e.target.id)||''; if(id==='btnNhAll'||id==='btnNhNone'||id==='btnEiAll'||id==='btnEiNone'){ var which = id.indexOf('Nh')!==-1? 'nhis':'ei'; var val = id.indexOf('All')!==-1; qsa('#calcConfigBody input[type="checkbox"][data-ins="'+which+'"]').forEach(function(cb){ cb.checked = val; }); try{ applyCalcConfigImmediate(); }catch(_){ } } });
    document.addEventListener('change', function(e){ var t=e.target; if(!(t instanceof HTMLElement)) return; if(t.matches && t.matches('#calcConfigBody input[type="checkbox"]')){ try{ applyCalcConfigImmediate(); }catch(_){ } } });
  }

  // 비과세 UI
  function openExemptConfig(){ buildExemptConfig(); var m=qs('#exemptConfigModal'); if(m) m.style.display='flex'; }
  function closeExemptConfig(){ var m=qs('#exemptConfigModal'); if(m) m.style.display='none'; }
  function buildExemptConfig(){
    var body = qs('#exemptConfigBody'); if(!body) return; body.innerHTML='';
    var classify = global.classify; var loadExemptOverrides = (global.PayrollState && global.PayrollState.loadExemptOverrides) || function(){ return {}; };
    var INS = global.INS || {}; var data = classify(); var ov = loadExemptOverrides(); var base = (INS.base_exemptions||{});
    (data.earnings||[]).forEach(function(t){ var field=t[0], label=t[1]; var key=field; var cur = ov[key] || { enabled: (base[label]!=null && Number(base[label])>0) || (base[key]!=null && Number(base[key])>0), limit: Number((base[label] ?? base[key] ?? 0)) };
      var tr = document.createElement('tr');
      tr.innerHTML = '<td class="col-name">'+label+'</td>'+
        '<td class="radio-cell"><label class="radio-wrap"><input class="as-radio" type="checkbox" data-ex="1" data-field="'+key+'" '+(cur.enabled?'checked':'')+'></label></td>'+
        '<td class="col-type"><input type="number" step="1" inputmode="numeric" data-limit="1" data-field="'+key+'" value="'+(cur.limit||0)+'" style="min-width:140px; text-align:right;"></td>';
      body.appendChild(tr);
    });
  }
  function commitExemptConfig(closeModal){
    var sanitizeNumeric = (global.PayrollUtils && PayrollUtils.sanitizeNumeric) || function(v){ return String(v||'').replace(/,/g,''); };
    var ov = {};
    qsa('#exemptConfigBody input[data-ex="1"]').forEach(function(ch){ var field=ch.dataset.field; var enabled=!!ch.checked; var limEl=qs('#exemptConfigBody input[data-limit="1"][data-field="'+CSS.escape(field)+'"]'); var raw= limEl? sanitizeNumeric(limEl.value):'0'; var limit = Math.max(0, Number(raw||0) || 0); ov[field] = enabled && limit>0 ? { enabled:true, limit:limit } : { enabled:false, limit:0 }; });
    if(global.PayrollState && PayrollState.saveExemptOverrides) PayrollState.saveExemptOverrides(ov);
    try{ fetch('/api/portal/'+encodeURIComponent(global.SLUG)+'/fields/exempt-config', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ exempt: ov }) }); }catch(_){ }
    try{ if(global.computeAll) global.computeAll(); }catch(_){ }
    if(closeModal !== false) closeExemptConfig();
  }
  function saveExemptConfig(){ commitExemptConfig(true); }

  function wireExemptListeners(){
    document.addEventListener('change', function(e){ var t=e.target; if(!(t instanceof HTMLElement)) return; if(t.matches && (t.matches('#exemptConfigBody input[data-ex="1"]') || t.matches('#exemptConfigBody input[data-limit="1"]'))){ try{ commitExemptConfig(false); }catch(_){ } } });
  }

  // export
  global.PayrollUI = global.PayrollUI || {
    openCalcConfig: openCalcConfig,
    closeCalcConfig: closeCalcConfig,
    buildCalcConfig: buildCalcConfig,
    saveCalcConfig: saveCalcConfig,
    applyCalcConfigImmediate: applyCalcConfigImmediate,
    openExemptConfig: openExemptConfig,
    closeExemptConfig: closeExemptConfig,
    buildExemptConfig: buildExemptConfig,
    saveExemptConfig: saveExemptConfig,
    commitExemptConfig: commitExemptConfig,
    wireCalcConfigListeners: wireCalcConfigListeners,
    wireExemptListeners: wireExemptListeners
  };
})(window);
