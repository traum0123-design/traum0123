(function(global){
  'use strict';
  var LOCALE = document.documentElement && document.documentElement.lang || 'ko-KR';
  var msgs = {};
  function fmtNumber(n){
    try{ return Number(n).toLocaleString(LOCALE); }catch(e){ return String(n); }
  }
  function fmtCurrency(n, currency){
    try{ return new Intl.NumberFormat(LOCALE, {style:'currency', currency: currency || 'KRW', maximumFractionDigits:0}).format(Number(n||0)); }catch(e){ return fmtNumber(n); }
  }
  function fmtDate(d){
    try{
      var date = d instanceof Date ? d : new Date(d);
      return new Intl.DateTimeFormat(LOCALE, {year:'numeric', month:'2-digit', day:'2-digit'}).format(date);
    }catch(e){ return String(d||''); }
  }
  function t(key, fallback){
    if(!key) return String(fallback||'');
    var v = msgs[key];
    return (typeof v === 'string') ? v : String(fallback||'');
  }
  function applyI18n(){
    try{
      document.querySelectorAll('[data-i18n]').forEach(function(el){
        var key = el.getAttribute('data-i18n');
        var val = t(key, el.textContent);
        if(val) el.textContent = val;
      });
      document.querySelectorAll('[data-i18n-placeholder]').forEach(function(el){
        var key = el.getAttribute('data-i18n-placeholder');
        var val = t(key, el.getAttribute('placeholder'));
        if(val) el.setAttribute('placeholder', val);
      });
    }catch(e){ /* no-op */ }
  }
  function loadMessages(){
    var path = '/static/i18n/ko.json';
    try {
      fetch(path, {cache: 'no-store'})
        .then(function(r){ if(!r.ok) throw new Error('failed'); return r.json(); })
        .then(function(json){ msgs = json || {}; applyI18n(); })
        .catch(function(){ /* ignore */ });
    } catch(e) { /* ignore */ }
  }
  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', function(){ loadMessages(); applyI18n(); });
  }else{
    loadMessages(); applyI18n();
  }
  global.I18N = global.I18N || { fmtNumber: fmtNumber, fmtCurrency: fmtCurrency, fmtDate: fmtDate, t: t };
})(window);
