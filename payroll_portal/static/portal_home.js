(function(global){
  'use strict';
  function currentYear(){
    const el = global.document.getElementById('currentYear');
    if(el){ const v = parseInt(el.value, 10); if(!Number.isNaN(v)) return v; }
    return new Date().getFullYear();
  }
  function changeYear(delta){
    const params = new URLSearchParams(global.location.search);
    const next = currentYear() + Number(delta || 0);
    params.set('year', next);
    const path = global.location.pathname.split('?')[0];
    global.location.href = `${path}?${params.toString()}`;
  }
  document.addEventListener('click', (event)=>{
    const prev = event.target.closest('[data-action="changeYearPrev"]');
    const next = event.target.closest('[data-action="changeYearNext"]');
    if(!prev && !next) return;
    event.preventDefault();
    if(prev) changeYear(-1); else changeYear(1);
  });
  global.changeYear = changeYear;
})(window);
