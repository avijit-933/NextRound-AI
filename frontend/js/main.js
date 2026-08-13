/* =========================================================
   NEXTROUND AI — shared front-end behaviour
   Everything here is a working prototype: mock data + real UI
   interactions. Swap the MOCK_API calls for real fetch() calls
   to your FastAPI backend when it's ready.
========================================================= */

/* ---------- THEME ---------- */
(function initTheme(){
  const saved = localStorage.getItem('nr-theme') || 'light';
  document.documentElement.setAttribute('data-theme', saved);
})();

function toggleTheme(){
  const root = document.documentElement;
  const next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  root.setAttribute('data-theme', next);
  localStorage.setItem('nr-theme', next);
  document.querySelectorAll('.theme-toggle i').forEach(i=>{
    i.className = next === 'dark' ? 'bi bi-moon-stars' : 'bi bi-sun';
  });
}

/* ---------- REVEAL ON SCROLL ---------- */
document.addEventListener('DOMContentLoaded', () => {
  const els = document.querySelectorAll('.reveal');
  if('IntersectionObserver' in window && els.length){
    const io = new IntersectionObserver((entries)=>{
      entries.forEach(e=>{
        if(e.isIntersecting){ e.target.classList.add('is-visible'); io.unobserve(e.target); }
      });
    },{threshold:.12});
    els.forEach(el=>io.observe(el));
  } else {
    els.forEach(el=>el.classList.add('is-visible'));
  }
});

/* ---------- MOBILE SIDEBAR ---------- */
function toggleSidebar(){
  document.querySelector('.app-sidebar')?.classList.toggle('open');
}

/* ---------- TOASTS ---------- */
function showToast(message, type='info'){
  let stack = document.querySelector('.nr-toast-stack');
  if(!stack){
    stack = document.createElement('div');
    stack.className = 'nr-toast-stack';
    document.body.appendChild(stack);
  }
  const icons = { success:'bi-check-circle-fill', danger:'bi-exclamation-triangle-fill', info:'bi-info-circle-fill' };
  const toast = document.createElement('div');
  toast.className = `nr-toast ${type}`;
  toast.innerHTML = `<i class="bi ${icons[type]||icons.info}"></i><div style="font-size:.88rem;">${message}</div>`;
  stack.appendChild(toast);
  setTimeout(()=>{
    toast.style.transition='opacity .3s ease, transform .3s ease';
    toast.style.opacity='0'; toast.style.transform='translateX(30px)';
    setTimeout(()=>toast.remove(), 300);
  }, 3600);
}

/* ---------- READINESS RING HELPER ---------- */
function setRing(el, pct, color){
  el.style.setProperty('--pct', pct);
  if(color) el.style.setProperty('--ring-color', color);
  const numEl = el.querySelector('.num');
  if(numEl) numEl.textContent = Math.round(pct);
}
function scoreColor(pct){
  if(pct >= 75) return 'var(--success)';
  if(pct >= 50) return 'var(--warning)';
  return 'var(--danger)';
}

/* ---------- AUTH (real backend — see js/api.js for Auth/AuthAPI) ---------- */
function requireAuth(){
  if (typeof Auth === 'undefined' || !Auth.isLoggedIn()) {
    window.location.href = 'login.html';
  }
}

function doLogout(e){
  if (e) e.preventDefault();
  Auth.clearSession();
  window.location.href = 'index.html';
}

function paintUserBadges(){
  const user = (typeof Auth !== 'undefined') ? Auth.getUser() : null;
  if(!user) return;
  document.querySelectorAll('[data-user-name]').forEach(el=>el.textContent = user.full_name || user.name);
  document.querySelectorAll('[data-user-email]').forEach(el=>el.textContent = user.email);
  document.querySelectorAll('[data-user-initial]').forEach(el=>el.textContent = (user.full_name || user.name || '?').charAt(0).toUpperCase());

  // The initial letter above is just the fallback. If this user has
  // actually uploaded a photo, replace it with the real image everywhere
  // the avatar shows up (navbar, sidebar, profile page big avatar, etc).
  if (typeof UsersAPI !== 'undefined') {
    UsersAPI.getProfile()
      .then(profile => paintAvatarImage(profile && profile.profile_picture_url))
      .catch(()=>{ /* not logged in on this page, or no profile yet — keep initials */ });
  }
}

/**
 * Swaps every [data-user-initial] avatar element between the initial-letter
 * fallback and a real <img>. Called on page load (via paintUserBadges) and
 * again immediately after a successful photo upload on profile.html, so
 * every page — dashboard included — reflects the new picture without a
 * refresh being needed the next time it loads.
 */
function paintAvatarImage(url){
  document.querySelectorAll('[data-user-initial]').forEach(el => {
    let img = el.querySelector('img');
    if (url) {
      if (!img) {
        img = document.createElement('img');
        img.style.cssText = 'width:100%;height:100%;object-fit:cover;border-radius:50%;';
        el.textContent = '';
        el.appendChild(img);
      }
      // cache-bust so a re-uploaded photo with the same filename still refreshes
      img.src = url + (url.includes('?') ? '&' : '?') + 't=' + Date.now();
    } else if (img) {
      img.remove();
    }
  });
}

/* ---------- NAV ACTIVE STATE + AUTH-AWARE NAV BUTTONS ---------- */
document.addEventListener('DOMContentLoaded', ()=>{
  const path = window.location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.nr-navbar .nav-link, .side-link').forEach(link=>{
    if(link.getAttribute('href') === path) link.classList.add('active');
  });
  paintUserBadges();

  const user = (typeof Auth !== 'undefined') ? Auth.getUser() : null;
  if (!user || !user.is_admin) {
    document.querySelectorAll('a[href="admin.html"].side-link').forEach(link => link.style.display = 'none');
  }
});
