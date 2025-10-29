(function(global){
  'use strict';
  function sanitizeNumeric(value){
    if(value === null || value === undefined) return '';
    var raw = String(value).replace(/[^0-9.,-]/g, '').replace(/,/g, '');
    if(raw.indexOf('-') !== -1){
      var negative = raw.charAt(0) === '-';
      raw = raw.replace(/-/g, '');
      if(negative) raw = '-' + raw;
    }
    return raw;
  }
  function formatNumeric(value){
    var raw = sanitizeNumeric(value);
    if(raw === '' || raw === '-' || raw === '.') return raw;
    var num = Number(raw);
    if(!isFinite(num)) return raw;
    return num.toLocaleString('ko-KR');
  }
  function markNegative(el, val){
    try{
      var n = Number(String(val != null ? val : (el && el.value) || '').replace(/,/g,'').trim()||0);
      if(isFinite(n) && n < 0){ el && el.classList && el.classList.add('neg'); }
      else { el && el.classList && el.classList.remove('neg'); }
    }catch(e){ try{ el && el.classList && el.classList.remove('neg'); }catch(_){ } }
  }
  // rAF-based debounced scheduler
  function createRafScheduler(fn){
    var scheduled = false;
    var raf = global.requestAnimationFrame || function(cb){ return setTimeout(cb, 0); };
    return function(){ if(scheduled) return; scheduled = true; raf(function(){ scheduled = false; try{ fn(); }catch(_){ } }); };
  }
  global.PayrollUtils = global.PayrollUtils || {
    sanitizeNumeric: sanitizeNumeric,
    formatNumeric: formatNumeric,
    markNegative: markNegative,
    createRafScheduler: createRafScheduler
  };
})(window);

