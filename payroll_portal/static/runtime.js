(function(){
  'use strict';

  function setCsrf(){
    try{
      const meta = document.querySelector('meta[name="csrf-token"]');
      window.__CSRF__ = meta ? meta.getAttribute('content') : '';
    }catch(_){ window.__CSRF__ = ''; }
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

  setCsrf();
  initModals();
})();

