// Global small UX helpers
(function(){
  // CSRF helper: attach token header when meta tag is present
  try{
    const meta = document.querySelector('meta[name="csrf-token"]');
    if(!meta) return;
    const csrf = (meta.getAttribute('content') || '').trim();
    if(!csrf) return;
    const originalFetch = window.fetch;
    window.fetch = function(input, init){
      init = init || {};
      const headers = init.headers instanceof Headers ? init.headers : new Headers(init.headers || {});
      if(!headers.has('X-CSRF-Token')){
        headers.set('X-CSRF-Token', csrf);
      }
      init.headers = headers;
      return originalFetch(input, init);
    };
  }catch(e){}
})();
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
