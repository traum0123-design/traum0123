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
  global.changeYear = changeYear;
})(window);
