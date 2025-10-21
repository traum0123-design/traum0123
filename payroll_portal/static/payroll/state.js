(function(global){
  'use strict';
  function nsKey(base){
    try{
      var slug = (global.SLUG||'').trim();
      if(slug) return base + '__' + slug;
    }catch(_){ }
    return base + '__default';
  }
  function loadInsIncludeMap(){
    try{
      var raw = JSON.parse(localStorage.getItem(nsKey('payroll_ins_include_v1')) || '{}');
      var norm = { nps:{}, nhis:{}, ei:{} };
      if(raw && typeof raw === 'object'){
        ['nps','nhis','ei'].forEach(function(k){ if(raw[k] && typeof raw[k] === 'object') norm[k] = Object.assign({}, raw[k]); });
      }
      return norm;
    }catch(e){ return { nps:{}, nhis:{}, ei:{} }; }
  }
  function saveInsIncludeMap(m){ try{ localStorage.setItem(nsKey('payroll_ins_include_v1'), JSON.stringify(m||{nps:{},nhis:{},ei:{}})); }catch(e){} }
  function loadExemptOverrides(){
    try{
      var raw = JSON.parse(localStorage.getItem(nsKey('payroll_exempt_overrides_v1')) || '{}');
      return (raw && typeof raw === 'object') ? raw : {};
    }catch(e){ return {}; }
  }
  function saveExemptOverrides(m){ try{ localStorage.setItem(nsKey('payroll_exempt_overrides_v1'), JSON.stringify(m||{})); }catch(e){} }
  global.PayrollState = global.PayrollState || {
    loadInsIncludeMap: loadInsIncludeMap,
    saveInsIncludeMap: saveInsIncludeMap,
    loadExemptOverrides: loadExemptOverrides,
    saveExemptOverrides: saveExemptOverrides
  };
})(window);
