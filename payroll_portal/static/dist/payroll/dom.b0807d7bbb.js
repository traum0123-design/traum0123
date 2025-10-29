(function(global){
  'use strict';
  function getInputInRow(tr, field, getColIndexByField){
    if(!tr) return null;
    try{
      var col = (typeof getColIndexByField==='function') ? getColIndexByField(field) : null;
      if(col!==null){
        var el = tr.querySelector('input[data-col="'+col+'"]');
        if(el) return el;
      }
      // Fallback: query by name suffix
      try{ return tr.querySelector('[name$="['+CSS.escape(field)+']"]'); }catch(_){ return tr.querySelector('[name$="['+field+']"]'); }
    }catch(e){ return null; }
  }
  function setMoney(input, value, options){
    if(!input) return;
    var raw = String(Math.round(Number(value)||0));
    try{ input.value = (input.type==='number') ? raw : (global.PayrollUtils ? PayrollUtils.formatNumeric(raw) : raw); }catch(e){ input.value = raw; }
    try{ if(global.PayrollUtils) PayrollUtils.markNegative(input, raw); }catch(_){ }
    if(!(options && options.silent)){
      try{ input.dispatchEvent(new Event('input', { bubbles:true })); }catch(_){ }
    }
  }
  function setMoneyByNames(tr, names, value, silent){
    if(!tr) return;
    var el = null;
    for(var i=0;i<names.length;i++){ el = global.getInputByNames ? global.getInputByNames(tr, [names[i]]) : null; if(el) break; }
    setMoney(el, value, { silent: !!silent });
  }
  global.PayrollDOM = global.PayrollDOM || {
    getInputInRow: getInputInRow,
    setMoney: setMoney,
    setMoneyByNames: setMoneyByNames
  };
})(window);

