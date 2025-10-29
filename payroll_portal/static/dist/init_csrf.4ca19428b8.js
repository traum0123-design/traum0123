(function(){
  try {
    var el = document.querySelector('meta[name="csrf-token"]');
    if (el) {
      window.__CSRF__ = el.getAttribute('content');
    }
  } catch (e) {
    // no-op
  }
})();

