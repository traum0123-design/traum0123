// Global small UX helpers
(function(){
  // CSRF helper: attach token to fetch if header missing
  try{
    const CSRF = window.__CSRF__ || (document.querySelector('meta[name="csrf-token"]').getAttribute('content'));
    const body = document.body || document.getElementsByTagName('body')[0];
    const API_BASE = (body && body.dataset ? (body.dataset.apiBase || '') : (window.API_BASE || '')).trim();
    const SHOULD_REWRITE = API_BASE && API_BASE !== '' && API_BASE !== '/api';
    const _fetch = window.fetch;
    function rewriteApiUrl(u){
      if(!SHOULD_REWRITE) return u;
      try{
        if(typeof u === 'string'){
          if(/^\/api\//.test(u) || /^\/portal\/[\w%-]+\/api\//.test(u) || /^\/admin\/[\w%-]+\/api\//.test(u)){
            return API_BASE.replace(/\/$/, '') + u;
          }
        }
      }catch(_){ }
      return u;
    }
    window.fetch = function(input, init){
      try{
        init = init || {};
        init.headers = init.headers || {};
        if(typeof init.headers === 'object' && !init.headers['X-CSRF-Token']){
          init.headers['X-CSRF-Token'] = CSRF;
        }
        // Attach API token for FastAPI auth if configured
        try{
          const tok = (window.API_TOKEN||'').trim();
          const atok = (window.ADMIN_TOKEN||'').trim();
          if(atok && (!init.headers['X-Admin-Token'])){ init.headers['X-Admin-Token'] = atok; }
          if(tok && (!init.headers['X-API-Token'])){ init.headers['X-API-Token'] = tok; }
          // Prefer admin token for /admin/ URLs, else company token
          if(typeof input === 'string' && input.startsWith('/admin/') && atok){
            if(!init.headers['Authorization']) init.headers['Authorization'] = 'Bearer ' + atok;
          }else if(tok){
            if(!init.headers['Authorization']) init.headers['Authorization'] = 'Bearer ' + tok;
          }
        }catch(_){ }
      }catch(e){}
      try{
        if(typeof input === 'string') input = rewriteApiUrl(input);
      }catch(_){ }
      return _fetch(input, init);
    };
  }catch(e){}

  // Client error collection (best-effort, no block)
  (function(){
    function send(payload){
      try{
        fetch('/client-log', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
      }catch(e){}
    }
    window.addEventListener('error', function(ev){
      try{
        const e = ev.error || {};
        send({ kind:'onerror', message: ev.message || (e && e.message) || 'error', url: (ev.filename||location.href), line: ev.lineno||'', col: ev.colno||'', stack: (e && e.stack) || '', ua: navigator.userAgent, level:'error' });
      }catch(_){ }
    });
    window.addEventListener('unhandledrejection', function(ev){
      try{
        const reason = ev.reason || {};
        send({ kind:'unhandledrejection', message: (reason && (reason.message||reason.toString())) || 'unhandledrejection', url: location.href, stack: (reason && reason.stack) || '', ua: navigator.userAgent, level:'error' });
      }catch(_){ }
    });
  })();

  // Auto-dismiss flash messages
  const flashes = document.querySelectorAll('.flash');
  function attachFlash(el){
    const t = setTimeout(()=>{
      el.style.transition = 'opacity .3s';
      el.style.opacity = '0';
      setTimeout(()=> el.remove(), 300);
    }, 3000);
    el.addEventListener('click', ()=>{ clearTimeout(t); el.remove(); });
  }
  flashes.forEach(attachFlash);

  window.PayrollFlash = function(type, message){
    if(!message) return;
    let area = document.querySelector('.flash-area');
    if(!area){
      area = document.createElement('div');
      area.className = 'flash-area';
      const container = document.querySelector('main.container');
      if(container){
        container.insertBefore(area, container.firstChild);
      }else{
        document.body.appendChild(area);
      }
    }
    const el = document.createElement('div');
    el.className = 'flash ' + (type || 'info');
    el.textContent = message;
    area.appendChild(el);
    attachFlash(el);
    return el;
  };
})();
