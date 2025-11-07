(function(global){
  'use strict';
  const SERVER_CALC_CACHE = new Map();
  const SERVER_CALC_TIMER = new WeakMap();
  const SERVER_CALC_LAST = new WeakMap();

  function collectRowPayload(tr){
    const data = {};
    try{
      tr.querySelectorAll('input[name]').forEach(function(inp){
        const name = inp.getAttribute('name') || '';
        const match = name.match(/\[([^\[\]]+)\]$/);
        if(!match) return;
        const field = match[1];
        if(field in data) return;
        if(inp.type === 'checkbox'){
          data[field] = inp.checked ? 1 : 0;
        }else{
          var val = inp.value;
          data[field] = (val === undefined || val === null) ? '' : val;
        }
      });
    }catch(_){ }
    const ordered = {};
    Object.keys(data).sort().forEach(function(key){ ordered[key] = data[key]; });
    return ordered;
  }

  function applyServerAmounts(tr, result){
    try{
      const setMoney = global.setMoneyByNames || function(){};
      const amounts = (result && result.amounts) || {};
      // Emit input events to sync UI proxies in real-time (non-silent)
      if(typeof amounts.national_pension === 'number'){ setMoney(tr, ['국민연금'], amounts.national_pension, false); }
      if(typeof amounts.health_insurance === 'number'){ setMoney(tr, ['건강보험','건강보험료'], amounts.health_insurance, false); }
      if(typeof amounts.long_term_care === 'number'){ setMoney(tr, ['장기요양보험','장기요양보험료','장기요양'], amounts.long_term_care, false); }
      if(typeof amounts.employment_insurance === 'number'){ setMoney(tr, ['고용보험','고용보험료'], amounts.employment_insurance, false); }
      if(typeof amounts.income_tax === 'number'){ setMoney(tr, ['소득세'], amounts.income_tax, false); }
      if(typeof amounts.local_income_tax === 'number'){ setMoney(tr, ['지방소득세'], amounts.local_income_tax, false); }
      try{ if(typeof updateSplitSummary === 'function') updateSplitSummary(); }catch(_){ }
    }catch(_){ }
  }

  async function fetchServerCalc(tr, payload, key){
    const cacheKey = key;
    if(SERVER_CALC_CACHE.has(cacheKey)){
      if(SERVER_CALC_LAST.get(tr) === key){
        applyServerAmounts(tr, SERVER_CALC_CACHE.get(cacheKey));
      }
      return;
    }
    try{
      const url = '/api/portal/'+encodeURIComponent(global.SLUG)+'/calc/deductions';
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify(payload)
      });
      const json = await res.json();
      if(!res.ok || !json || json.ok === false) return;
      SERVER_CALC_CACHE.set(cacheKey, json);
      if(SERVER_CALC_LAST.get(tr) === key){
        applyServerAmounts(tr, json);
      }
    }catch(_){ }
  }

  function scheduleServerCalc(tr, payload){
    // Include year/slug/month in cache key to avoid cross-year reuse
    const key = JSON.stringify({ y: (typeof YEAR!=='undefined'? YEAR : payload.year), m: (typeof MONTH!=='undefined'? MONTH : null), s: (typeof SLUG!=='undefined'? SLUG : null), row: (payload.row || {}) });
    SERVER_CALC_LAST.set(tr, key);
    if(SERVER_CALC_TIMER.has(tr)){
      clearTimeout(SERVER_CALC_TIMER.get(tr));
    }
    const timer = setTimeout(function(){
      SERVER_CALC_TIMER.delete(tr);
      fetchServerCalc(tr, payload, key);
    }, 60);
    SERVER_CALC_TIMER.set(tr, timer);
  }

  function computeDeductions(tr){
    if(!tr) return;
    var classify = global.classify;
    var getInputInRow = global.getInputInRow;
    var parseMoney = global.parseMoney;
    var setMoneyByNames = global.setMoneyByNames;
    var loadInsIncludeMap = (global.PayrollState && global.PayrollState.loadInsIncludeMap) || function(){ return { nps:{}, nhis:{}, ei:{} }; };
    var loadExemptOverrides = (global.PayrollState && global.PayrollState.loadExemptOverrides) || function(){ return {}; };
    var INS = global.INS || {};
    var YEAR = global.YEAR, SLUG = global.SLUG;
    var DEDUCTION_FIELDS = global.DEDUCTION_FIELDS || new Set(['국민연금','건강보험','장기요양보험','고용보험','소득세','지방소득세']);

    var groups = classify();
    // Row-level cache to cut repeated DOM queries
    var rowElCache = new Map();
    var rowGetEl = function(name){ if(rowElCache.has(name)) return rowElCache.get(name); var el = getInputInRow(tr, name); rowElCache.set(name, el); return el; };
    // Build values map for all earnings
    var earnVals = new Map();
    (groups.earnings || []).forEach(function(t){ var field=t[0]; var inp=rowGetEl(field); if(!inp) return; earnVals.set(field, parseMoney(inp)); });
    // Inclusion map (per insurance): if not configured, fall back to default logic
    var inc = loadInsIncludeMap();
    function sumSelected(sel){ var s=0; var seen=new Set(); Object.keys(sel||{}).forEach(function(f){ if(sel[f] && !seen.has(f)){ seen.add(f); if(earnVals.has(f)) s += (earnVals.get(f)||0); }}); return s; }
    // Default base (all earnings - exemptions)
    function getExemptMap(){
      var base = (INS.base_exemptions||{});
      var ov = loadExemptOverrides();
      var out = {};
      try{ Object.entries(base).forEach(function(kv){ var k=kv[0], v=kv[1]; out[k] = Math.max(0, Number(v)||0); }); }catch(_){ }
      try{ Object.entries(ov||{}).forEach(function(kv){ var field=kv[0], conf=kv[1]; if(!conf || typeof conf!=='object') return; var enabled=!!conf.enabled; var limit=Math.max(0, Number(conf.limit)||0); if(enabled && limit>0){ out[field]=limit; } else { delete out[field]; } }); }catch(_){ }
      return out;
    }
    function defaultBase(){
      var base = 0; var seen = new Set();
      (groups.earnings || []).forEach(function(t){ var field=t[0]; if(DEDUCTION_FIELDS.has(field)) return; if(seen.has(field)) return; seen.add(field); var v = earnVals.get(field)||0; base += v; });
      var exempt = getExemptMap();
      Object.entries(exempt).forEach(function(kv){ var name=kv[0], limit=kv[1]; var val = parseMoney(rowGetEl(name)); var ex = Math.max(0, Math.min(Number(limit)||0, val)); base -= ex; });
      return Math.max(0, base);
    }
    var base_nps  = (Object.keys(inc.nps||{}).length)  ? Math.max(0, sumSelected(inc.nps||{}))  : defaultBase();
    var nhSel = inc.nhis || {};
    var eiSel = inc.ei || {};
    function selectedBase(sel){
      var subtotal = Math.max(0, Number(sumSelected(sel))||0);
      // 비과세 한도가 있는 항목은 선택된 경우에 한해 차감
      try{
        var exmap = getExemptMap();
        Object.keys(exmap||{}).forEach(function(name){
          if(sel && sel[name]){
            var val = parseMoney(rowGetEl(name));
            var limit = Math.max(0, Number(exmap[name])||0);
            var ex = Math.max(0, Math.min(limit, val));
            subtotal -= ex;
          }
        });
      }catch(_){ }
      return Math.max(0, subtotal);
    }
    // 규칙: 선택이 있으면 '선택 항목만' 합산, 없으면 기본 규칙(defaultBase)
    var base_nhis = (Object.keys(nhSel).length) ? selectedBase(nhSel) : defaultBase();
    var base_ei   = (Object.keys(eiSel).length) ? selectedBase(eiSel) : defaultBase();

    function calcBy(cfg, rate, b){ b = Math.max(0, Number(b)||0); if(cfg && (cfg.min_base!=null)) b = Math.max(b, Number(cfg.min_base)||0); if(cfg && (cfg.max_base!=null)) b = Math.min(b, Number(cfg.max_base)||0); var amt = b * rate; var to = (cfg && cfg.round_to) || 10; var mode = (cfg && cfg.rounding) || 'round';
      if(mode==='floor') return Math.floor(amt/to)*to; if(mode==='ceil') return Math.ceil(amt/to)*to; return Math.round(amt/to)*to; }
    var np_cfg = INS.nps || {}; var hi_cfg = INS.nhis || {}; var ei_cfg = INS.ei || {};
    var baseNpsField = rowGetEl('기준보수월액'); var baseNps = baseNpsField ? parseMoney(baseNpsField) : 0;
    var np = calcBy(np_cfg, Number(np_cfg.rate||0.045), baseNps);
    var hi = calcBy(hi_cfg, Number(hi_cfg.rate||0.03545), base_nhis);
    var ltc_rate = (hi_cfg && hi_cfg.ltc_rate!=null) ? Number(hi_cfg.ltc_rate) : 0.1295;
    var ltc_to = (hi_cfg && hi_cfg.ltc_round_to!=null) ? Number(hi_cfg.ltc_round_to) : (hi_cfg.round_to||10);
    var ltc_mode = (hi_cfg && hi_cfg.ltc_rounding) || (hi_cfg.rounding||'round');
    var ltc = (function(hiAmt){ var amt = hiAmt * ltc_rate; if(ltc_mode==='floor') return Math.floor(amt/ltc_to)*ltc_to; if(ltc_mode==='ceil') return Math.ceil(amt/ltc_to)*ltc_to; return Math.round(amt/ltc_to)*ltc_to; })(hi);
    var ei = calcBy(ei_cfg, Number(ei_cfg.rate||0.009), base_ei);

    // Real-time updates: emit input events so split-view proxies sync immediately
    setMoneyByNames(tr, ['국민연금'], np, false);
    setMoneyByNames(tr, ['건강보험','건강보험료'], hi, false);
    setMoneyByNames(tr, ['장기요양보험','장기요양보험료','장기요양'], ltc, false);
    setMoneyByNames(tr, ['고용보험','고용보험료'], ei, false);

    try{
      var taxable = Math.max(0, Math.floor(defaultBase()||0));
      if(!taxable){
        setMoneyByNames(tr, ['소득세'], 0, false);
        setMoneyByNames(tr, ['지방소득세'], 0, false);
      }
      var payload = { year: YEAR, row: collectRowPayload(tr) };
      scheduleServerCalc(tr, payload);
    }catch(e){ }
  }
  global.PayrollCalc = global.PayrollCalc || { computeDeductions: computeDeductions };
})(window);
