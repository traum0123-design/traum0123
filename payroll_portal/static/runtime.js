(function(){
  'use strict';

  const CSRF_HEADER = 'X-CSRF-Token';

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

  setCsrf();
  patchFetch();
  initModals();
})();
