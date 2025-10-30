(function(){
  'use strict';

  const CSRF_HEADER = 'X-CSRF-Token';
  const UI_PREFS_ENABLED = (function(){
    try{
      const b = document.body;
      return !(b && b.dataset && b.dataset.uiPrefs === 'off');
    }catch(_){ return true; }
  })();

  function setCsrf(){
    try{
      const meta = document.querySelector('meta[name="csrf-token"]');
      window.__CSRF__ = meta ? meta.getAttribute('content') : '';
    }catch(_){ window.__CSRF__ = ''; }
  }

  function patchFetch(){
    if(!window.fetch || window.fetch.__csrf_patched) return;
    const originalFetch = window.fetch.bind(window);
    window.fetch = function(resource, init){
      const token = window.__CSRF__ || '';
      const options = init ? Object.assign({}, init) : {};
      const headers = new Headers(options.headers || {});
      if(token && !headers.has(CSRF_HEADER)){
        headers.set(CSRF_HEADER, token);
      }
      options.headers = headers;
      if(options.credentials === undefined){
        options.credentials = 'same-origin';
      }
      return originalFetch(resource, options);
    };
    window.fetch.__csrf_patched = true;
  }

  function initModals(){
    function wire(){
      try{ if(window.PayrollUI && PayrollUI.wireCalcConfigListeners){ PayrollUI.wireCalcConfigListeners(); } }catch(_){}
      try{ if(window.PayrollUI && PayrollUI.wireExemptListeners){ PayrollUI.wireExemptListeners(); } }catch(_){}
    }
    if(document.readyState === 'loading'){
      document.addEventListener('DOMContentLoaded', wire);
    }else{
      wire();
    }
  }

  // UI Prefs: apply saved table column widths and persist changes
  function applyTableColumnWidths(){
    if(!UI_PREFS_ENABLED) return;
    try{
      if(!window.SLUG) return;
      const head = document.querySelector('#payroll-table thead');
      if(!head) return;
      fetch(`/api/portal/${encodeURIComponent(window.SLUG)}/ui-prefs?keys=table.columnWidths`, { credentials: 'same-origin' })
        .then(r=>r.ok?r.json():null)
        .then(data=>{
          if(!data || !data.values) return;
          const map = data.values['table.columnWidths'] || {};
          Object.keys(map||{}).forEach(field=>{
            const th = head.querySelector(`th[data-field="${CSS.escape(field)}"]`);
            const w = parseInt(map[field], 10);
            if(th && w && w > 40 && w < 1000){ th.style.width = `${w}px`; }
          });
        })
        .catch(()=>{});
    }catch(_){ }
  }

  function applyViewMode(){
    if(!UI_PREFS_ENABLED) return;
    try{
      if(!window.SLUG) return;
      fetch(`/api/portal/${encodeURIComponent(window.SLUG)}/ui-prefs?keys=view.mode`, { credentials: 'same-origin' })
        .then(r=>r.ok?r.json():null)
        .then(data=>{
          if(!data || !data.values) return;
          const mode = (data.values['view.mode'] || '').toString();
          const body = document.body;
          if(!body) return;
          body.classList.toggle('view-compact', mode === 'compact');
        }).catch(()=>{});
    }catch(_){ }
  }

  function toggleViewMode(){
    if(!UI_PREFS_ENABLED) return;
    try{
      const body = document.body; if(!body) return;
      const next = body.classList.contains('view-compact') ? 'comfortable' : 'compact';
      body.classList.toggle('view-compact', next === 'compact');
      if(window.SLUG){
        fetch(`/api/portal/${encodeURIComponent(window.SLUG)}/ui-prefs`, {
          method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ values: { 'view.mode': next } })
        }).catch(()=>{});
      }
    }catch(_){ }
  }

  // Row density (compact / comfortable / tall)
  function setRowDensity(mode){
    if(!UI_PREFS_ENABLED) return;
    try{
      const body = document.body; if(!body) return;
      body.classList.remove('row-density-compact', 'row-density-tall');
      if(mode === 'compact') body.classList.add('row-density-compact');
      else if(mode === 'tall') body.classList.add('row-density-tall');
    }catch(_){ }
  }

  function applyRowDensity(){
    if(!UI_PREFS_ENABLED) return;
    try{
      if(!window.SLUG) return;
      fetch(`/api/portal/${encodeURIComponent(window.SLUG)}/ui-prefs?keys=view.rowDensity`, { credentials: 'same-origin' })
        .then(r=>r.ok?r.json():null)
        .then(data=>{
          if(!data || !data.values) return;
          const mode = (data.values['view.rowDensity'] || 'comfortable').toString();
          setRowDensity(mode);
        }).catch(()=>{});
    }catch(_){ }
  }

  const ROW_DENSITY_ORDER = ['comfortable','compact','tall'];
  function toggleRowDensity(){
    if(!UI_PREFS_ENABLED) return;
    try{
      const body = document.body; if(!body) return;
      const cur = body.classList.contains('row-density-compact') ? 'compact' : (body.classList.contains('row-density-tall') ? 'tall' : 'comfortable');
      const idx = ROW_DENSITY_ORDER.indexOf(cur);
      const next = ROW_DENSITY_ORDER[(idx + 1) % ROW_DENSITY_ORDER.length];
      setRowDensity(next);
      if(window.SLUG){
        fetch(`/api/portal/${encodeURIComponent(window.SLUG)}/ui-prefs`, {
          method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ values: { 'view.rowDensity': next } })
        }).catch(()=>{});
      }
    }catch(_){ }
  }

  function wireViewModeToggle(){
    if(!UI_PREFS_ENABLED) return;
    // Toggle with Shift+M (non-invasive)
    window.addEventListener('keydown', function(ev){
      try{
        if(ev.key && (ev.key.toLowerCase() === 'm') && ev.shiftKey){
          ev.preventDefault(); toggleViewMode();
        }
        if(ev.key && (ev.key.toLowerCase() === 'd') && ev.shiftKey){
          ev.preventDefault(); toggleRowDensity();
        }
      }catch(_){ }
    });
    // Toolbar buttons
    document.addEventListener('click', function(ev){
      const btn = ev.target && ev.target.closest ? ev.target.closest('[data-action]') : null;
      if(!btn) return;
      const act = btn.getAttribute('data-action') || '';
      if(act === 'toggleCompact'){ ev.preventDefault(); toggleViewMode(); }
      if(act === 'toggleFixedCols'){ ev.preventDefault(); toggleFixedCols(); }
      if(act === 'toggleRowDensity'){ ev.preventDefault(); toggleRowDensity(); }
      if(act === 'resetLayout'){ ev.preventDefault(); resetUILayout(); }
    });
  }

  function resetUILayout(){
    if(!UI_PREFS_ENABLED) return;
    try{
      if(!window.SLUG) return;
      // Reset prefs to defaults
      fetch(`/api/portal/${encodeURIComponent(window.SLUG)}/ui-prefs`, {
        method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ values: { 'table.columnWidths': {}, 'table.fixedCols': 0, 'view.mode': 'comfortable', 'view.rowDensity': 'comfortable' } })
      }).then(()=>{
        // Apply defaults immediately
        document.body.classList.remove('view-compact','row-density-compact','row-density-tall');
        setStickyColumns(0);
        // Clear explicit widths
        const head = document.querySelector('#payroll-table thead');
        if(head){ head.querySelectorAll('th[data-field]').forEach(th=> th.style.width=''); }
      }).catch(()=>{});
    }catch(_){ }
  }

  function gatherTableColumnWidths(){
    if(!UI_PREFS_ENABLED) return {};
    const head = document.querySelector('#payroll-table thead');
    if(!head) return {};
    const out = {};
    head.querySelectorAll('th[data-field]').forEach(th=>{
      const field = th.getAttribute('data-field') || '';
      const w = Math.round((th.getBoundingClientRect ? th.getBoundingClientRect().width : th.offsetWidth) || 0);
      if(field && w){ out[field] = w; }
    });
    return out;
  }

  let saveWidthsTimer = null;
  function scheduleSaveTableColumnWidths(){
    if(!UI_PREFS_ENABLED) return;
    try{
      if(!window.SLUG) return;
      clearTimeout(saveWidthsTimer);
      saveWidthsTimer = setTimeout(()=>{
        const map = gatherTableColumnWidths();
        fetch(`/api/portal/${encodeURIComponent(window.SLUG)}/ui-prefs`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify({ values: { 'table.columnWidths': map } })
        }).catch(()=>{});
      }, 400);
    }catch(_){ }
  }

  function wireTableWidthPersistence(){
    if(!UI_PREFS_ENABLED) return;
    const head = document.querySelector('#payroll-table thead');
    if(!head) return;
    // Save on mouseup in header (after potential drag), and on beforeunload
    head.addEventListener('mouseup', (ev)=>{ scheduleSaveTableColumnWidths(); });
    head.addEventListener('keydown', (ev)=>{
      const t = ev.target;
      if(!(t && t.classList && t.classList.contains('col-resizer'))) return;
      const th = t.closest('th');
      if(!th) return;
      let w = Math.round((th.getBoundingClientRect ? th.getBoundingClientRect().width : th.offsetWidth) || 0);
      if(ev.key === 'ArrowRight'){ ev.preventDefault(); th.style.width = (w+10) + 'px'; scheduleSaveTableColumnWidths(); }
      if(ev.key === 'ArrowLeft'){ ev.preventDefault(); th.style.width = Math.max(40, w-10) + 'px'; scheduleSaveTableColumnWidths(); }
      if(ev.key === 'Enter'){ ev.preventDefault(); scheduleSaveTableColumnWidths(); }
    });
    head.addEventListener('dblclick', (ev)=>{
      const t = ev.target;
      if(!(t && t.classList && t.classList.contains('col-resizer'))) return;
      const th = t.closest('th');
      if(!th) return;
      th.style.width = '';
      scheduleSaveTableColumnWidths();
    });
    window.addEventListener('beforeunload', ()=>{ try{ scheduleSaveTableColumnWidths(); }catch(_){ } });
  }

  // Sticky columns (fixed left N columns)
  function clearSticky(table){
    try{
      table.querySelectorAll('.sticky-col').forEach(el=>{
        el.classList.remove('sticky-col');
        el.style.left = '';
      });
    }catch(_){ }
  }

  function setStickyColumns(n){
    if(!UI_PREFS_ENABLED) return;
    try{
      const table = document.getElementById('payroll-table');
      if(!table) return;
      clearSticky(table);
      const headRow = table.querySelector('thead tr');
      if(!headRow) return;
      const ths = Array.from(headRow.children);
      const tbody = table.querySelector('tbody');
      const rows = tbody ? Array.from(tbody.children) : [];
      let left = 0;
      const max = Math.max(0, Math.min(n||0, ths.length));
      for(let k=0;k<max;k++){
        const th = ths[k];
        if(!th) continue;
        th.classList.add('sticky-col');
        th.style.left = left + 'px';
        const w = Math.round((th.getBoundingClientRect ? th.getBoundingClientRect().width : th.offsetWidth) || 0);
        rows.forEach(tr=>{
          const td = tr.children[k];
          if(td){ td.classList.add('sticky-col'); td.style.left = left + 'px'; }
        });
        left += w;
      }
    }catch(_){ }
  }

  function applyFixedColsFromPrefs(){
    if(!UI_PREFS_ENABLED) return;
    try{
      if(!window.SLUG) return;
      fetch(`/api/portal/${encodeURIComponent(window.SLUG)}/ui-prefs?keys=table.fixedCols`, { credentials: 'same-origin' })
        .then(r=>r.ok?r.json():null)
        .then(data=>{
          if(!data || !data.values) return;
          const n = parseInt((data.values['table.fixedCols']||0), 10) || 0;
          setStickyColumns(n);
        }).catch(()=>{});
    }catch(_){ }
  }

  let fixedCols = 0;
  function toggleFixedCols(){
    if(!UI_PREFS_ENABLED) return;
    try{
      const headRow = document.querySelector('#payroll-table thead tr');
      if(!headRow) return;
      const max = Math.min(4, headRow.children.length); // cap
      fixedCols = (fixedCols + 1) % (max+1);
      setStickyColumns(fixedCols);
      if(window.SLUG){
        fetch(`/api/portal/${encodeURIComponent(window.SLUG)}/ui-prefs`, {
          method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ values: { 'table.fixedCols': fixedCols } })
        }).catch(()=>{});
      }
    }catch(_){ }
  }

  function wireFixedColsToggle(){
    if(!UI_PREFS_ENABLED) return;
    window.addEventListener('keydown', function(ev){
      try{
        if(ev.key && (ev.key.toLowerCase() === 'f') && ev.shiftKey){ ev.preventDefault(); toggleFixedCols(); }
      }catch(_){ }
    });
  }

  // Global confirm handler (CSP-safe) for forms with data-confirm
  function wireConfirmDialogs(){
    try{
      document.addEventListener('submit', function(ev){
        const form = ev.target && ev.target.closest ? ev.target.closest('form[data-confirm]') : null;
        if(!form) return;
        const msg = form.getAttribute('data-confirm') || '정말 진행하시겠습니까?';
        const ok = window.confirm(msg);
        if(!ok){ ev.preventDefault(); ev.stopPropagation(); }
      }, true);
    }catch(_){ }
  }

  setCsrf();
  patchFetch();
  initModals();
  // UI Prefs sync
  if(UI_PREFS_ENABLED){
    if(document.readyState === 'loading'){
      document.addEventListener('DOMContentLoaded', function(){ applyTableColumnWidths(); wireTableWidthPersistence(); applyFixedColsFromPrefs(); wireFixedColsToggle(); applyViewMode(); applyRowDensity(); wireViewModeToggle(); wireConfirmDialogs(); });
    }else{
      applyTableColumnWidths(); wireTableWidthPersistence(); applyFixedColsFromPrefs(); wireFixedColsToggle(); applyViewMode(); applyRowDensity(); wireViewModeToggle(); wireConfirmDialogs();
    }
  }
})();
