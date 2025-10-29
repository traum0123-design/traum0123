(function(global){
  'use strict';
  var LOCALE = document.documentElement && document.documentElement.lang || 'ko-KR';
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
  global.I18N = global.I18N || { fmtNumber: fmtNumber, fmtCurrency: fmtCurrency, fmtDate: fmtDate };
})(window);

