/**
 * enhancements.js — FuseBypass visual upgrade layer v2
 * Injects CSS directly into <head> immediately, then runs JS effects.
 */

/* ═══════════════════════════════════════════════════════════════════
   STEP 1 — Inject all CSS immediately (no defer issues)
═══════════════════════════════════════════════════════════════════ */
(function injectCSS() {
  var css = `
    /* ── Cursor glow ── */
    #fuse-cursor-glow {
      position: fixed;
      pointer-events: none;
      z-index: 9990;
      width: 500px;
      height: 500px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(65,151,250,0.08) 0%, rgba(65,151,250,0.03) 40%, transparent 70%);
      transform: translate(-50%, -50%);
      left: -9999px;
      top: -9999px;
      transition: left 0.08s linear, top 0.08s linear;
      will-change: left, top;
    }

    /* ── Particle overlay canvas ── */
    #fuse-overlay-canvas {
      position: fixed;
      inset: 0;
      width: 100%;
      height: 100%;
      z-index: -1;
      pointer-events: none;
    }

    /* ── Nav active underline ── */
    .nav-item {
      position: relative;
    }
    .nav-item::after {
      content: "";
      position: absolute;
      bottom: -6px;
      left: 0;
      right: 0;
      height: 2px;
      background: #4197fa;
      border-radius: 2px;
      transform: scaleX(0);
      transition: transform 0.22s cubic-bezier(0.22, 1, 0.36, 1);
      transform-origin: center;
    }
    .nav-item.active::after {
      transform: scaleX(1);
    }

    /* ── Nav scroll shrink ── */
    #main-nav.scrolled {
      background: rgba(0, 0, 0, 0.95) !important;
      border-bottom: 1px solid rgba(255, 255, 255, 0.07) !important;
      box-shadow: 0 2px 40px rgba(0, 0, 0, 0.7) !important;
    }

    /* ── Page enter animation ── */
    @keyframes fusePageIn {
      from { opacity: 0; transform: translateY(12px); }
      to   { opacity: 1; transform: translateY(0); }
    }
    .page.active {
      animation: fusePageIn 0.32s cubic-bezier(0.22, 1, 0.36, 1) both !important;
    }

    /* ── Button ripple ── */
    .btn-primary,
    .btn-ghost,
    .btn-submit,
    .btn-discord,
    .nav-signup {
      position: relative;
      overflow: hidden;
    }
    .fuse-ripple {
      position: absolute;
      border-radius: 50%;
      background: rgba(255, 255, 255, 0.22);
      transform: scale(0);
      animation: fuseRippleAnim 0.55s ease-out forwards;
      pointer-events: none;
    }
    @keyframes fuseRippleAnim {
      to { transform: scale(4); opacity: 0; }
    }

    /* ── Card 3D tilt ── */
    .fuse-tilt-card {
      transform-style: preserve-3d;
      will-change: transform;
    }

    /* ── Scanner row blue left accent ── */
    .scanner-row {
      position: relative;
      transition: background 0.2s ease, box-shadow 0.2s ease !important;
    }
    .scanner-row::before {
      content: "";
      position: absolute;
      left: 0; top: 15%; bottom: 15%;
      width: 2px;
      background: linear-gradient(180deg, transparent, #4197fa, transparent);
      border-radius: 2px;
      opacity: 0;
      transition: opacity 0.2s ease;
    }
    .scanner-row:hover::before { opacity: 1; }
    .scanner-row:hover {
      box-shadow: inset 3px 0 0 rgba(65, 151, 250, 0.3) !important;
    }

    /* ── FAQ open border glow ── */
    .faq-item.open {
      border-color: rgba(65, 151, 250, 0.35) !important;
      box-shadow: 0 0 0 1px rgba(65, 151, 250, 0.12), 0 8px 32px rgba(0, 0, 0, 0.3) !important;
    }

    /* ── Store card hover glow ── */
    #page-store .fuse-tilt-card:hover {
      border-color: rgba(255, 255, 255, 0.2) !important;
      box-shadow: 0 20px 60px rgba(0, 0, 0, 0.6), 0 0 60px rgba(65, 151, 250, 0.07) !important;
    }

    /* ── Glass card hover shimmer ── */
    .tos-item,
    .faq-item {
      position: relative;
      overflow: hidden;
    }
    .tos-item::after,
    .faq-item::after {
      content: "";
      position: absolute;
      inset: 0;
      background: linear-gradient(105deg, transparent 40%, rgba(255,255,255,0.035) 50%, transparent 60%);
      background-size: 200% 100%;
      background-position: 200% 0;
      transition: background-position 0.55s ease;
      pointer-events: none;
    }
    .tos-item:hover::after,
    .faq-item:hover::after {
      background-position: -200% 0;
    }

    /* ── Loading bar blue ── */
    .logo-intro-bar-fill {
      background: linear-gradient(90deg, rgba(65,151,250,0.6), #4197fa, #ffffff) !important;
    }

    /* ── Badge undetected stronger glow ── */
    .badge-undetected {
      box-shadow: 0 0 16px rgba(0, 180, 60, 0.3) !important;
    }

    /* ── Footer glow ── */
    .site-footer {
      box-shadow: 0 -1px 0 rgba(255,255,255,0.06) !important;
    }

    /* ── Scroll reveal ── */
    .fuse-reveal {
      opacity: 0;
      transform: translateY(20px);
      transition: opacity 0.55s cubic-bezier(0.22, 1, 0.36, 1),
                  transform 0.55s cubic-bezier(0.22, 1, 0.36, 1);
    }
    .fuse-reveal.fuse-visible {
      opacity: 1;
      transform: translateY(0);
    }
    .fuse-reveal-d1 { transition-delay: 0.08s; }
    .fuse-reveal-d2 { transition-delay: 0.16s; }
    .fuse-reveal-d3 { transition-delay: 0.24s; }
    .fuse-reveal-d4 { transition-delay: 0.32s; }

    /* ── Floating badge enhanced shadow ── */
    .float-badge {
      box-shadow:
        0 4px 24px rgba(0, 0, 0, 0.65),
        0 0 0 1px rgba(255, 255, 255, 0.07),
        inset 0 1px 0 rgba(255, 255, 255, 0.09) !important;
    }

    /* ── Hero text glow ── */
    .hero-sub {
      filter: drop-shadow(0 0 40px rgba(65, 151, 250, 0.12));
    }
  `;
  var style = document.createElement('style');
  style.id = 'fuse-enhancements-css';
  style.textContent = css;
  document.head.appendChild(style);
})();

/* ═══════════════════════════════════════════════════════════════════
   STEP 2 — JS effects (run after DOM ready)
═══════════════════════════════════════════════════════════════════ */
function fuseInit() {

  /* ── 1. Cursor glow ── */
  var glow = document.createElement('div');
  glow.id = 'fuse-cursor-glow';
  document.body.appendChild(glow);

  var targetX = -9999, targetY = -9999;
  var glowX = -9999, glowY = -9999;

  document.addEventListener('mousemove', function(e) {
    targetX = e.clientX;
    targetY = e.clientY;
  });

  (function lerpGlow() {
    glowX += (targetX - glowX) * 0.1;
    glowY += (targetY - glowY) * 0.1;
    glow.style.left = glowX + 'px';
    glow.style.top  = glowY + 'px';
    requestAnimationFrame(lerpGlow);
  })();

  /* ── 2. Nav scroll effect ── */
  var nav = document.getElementById('main-nav');
  if (nav) {
    window.addEventListener('scroll', function() {
      nav.classList.toggle('scrolled', window.scrollY > 12);
    }, { passive: true });
  }

  /* ── 3. Button ripple ── */
  document.addEventListener('click', function(e) {
    var btn = e.target.closest('.btn-primary,.btn-ghost,.btn-submit,.btn-discord,.nav-signup');
    if (!btn) return;
    var rect = btn.getBoundingClientRect();
    var size = Math.max(rect.width, rect.height) * 1.6;
    var r = document.createElement('span');
    r.className = 'fuse-ripple';
    r.style.width  = size + 'px';
    r.style.height = size + 'px';
    r.style.left   = (e.clientX - rect.left - size / 2) + 'px';
    r.style.top    = (e.clientY - rect.top  - size / 2) + 'px';
    btn.appendChild(r);
    setTimeout(function() { r.remove(); }, 600);
  });

  /* ── 4. 3D card tilt ── */
  function applyTilt(selector) {
    document.querySelectorAll(selector).forEach(function(card) {
      if (card.dataset.fuseHasTilt) return;
      card.dataset.fuseHasTilt = '1';
      card.classList.add('fuse-tilt-card');
      card.style.transition = 'transform 0.4s cubic-bezier(0.22,1,0.36,1), box-shadow 0.25s, border-color 0.25s';

      card.addEventListener('mousemove', function(e) {
        var rect = card.getBoundingClientRect();
        var x = (e.clientX - rect.left) / rect.width  - 0.5;
        var y = (e.clientY - rect.top)  / rect.height - 0.5;
        card.style.transition = 'transform 0.08s ease, box-shadow 0.25s, border-color 0.25s';
        card.style.transform = 'perspective(800px) rotateX(' + (-y * 7) + 'deg) rotateY(' + (x * 7) + 'deg) translateY(-6px) scale(1.02)';
      });
      card.addEventListener('mouseleave', function() {
        card.style.transition = 'transform 0.45s cubic-bezier(0.22,1,0.36,1), box-shadow 0.25s, border-color 0.25s';
        card.style.transform = '';
      });
    });
  }

  applyTilt('#page-store > div > div');

  /* ── 5. Scroll reveal observer ── */
  var io = window.IntersectionObserver
    ? new IntersectionObserver(function(entries) {
        entries.forEach(function(entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add('fuse-visible');
            io.unobserve(entry.target);
          }
        });
      }, { threshold: 0.1, rootMargin: '0px 0px -30px 0px' })
    : null;

  function attachReveal(container) {
    var sel = [
      '.tos-item',
      '.faq-item',
      '.scanner-row',
      '.game-card',
      '#page-store > div > div',
    ];
    sel.forEach(function(s) {
      var scope = container || document;
      scope.querySelectorAll(s).forEach(function(el, i) {
        if (el.dataset.fuseReveal) return;
        el.dataset.fuseReveal = '1';
        el.classList.add('fuse-reveal', 'fuse-reveal-d' + ((i % 4) + 1));
        if (io) io.observe(el);
      });
    });
  }
  attachReveal();

  /* ── 6. Particle overlay canvas ── */
  var overlay = document.createElement('canvas');
  overlay.id = 'fuse-overlay-canvas';
  document.body.appendChild(overlay);

  var oc = overlay.getContext('2d');
  var pts = [];
  var N = 50;

  function resizeOv() {
    overlay.width  = window.innerWidth;
    overlay.height = window.innerHeight;
  }
  resizeOv();
  window.addEventListener('resize', resizeOv, { passive: true });

  for (var i = 0; i < N; i++) {
    pts.push({
      x:  Math.random() * window.innerWidth,
      y:  Math.random() * window.innerHeight,
      vx: (Math.random() - 0.5) * 0.22,
      vy: (Math.random() - 0.5) * 0.22,
      r:  0.6 + Math.random() * 1.4,
      a:  0.12 + Math.random() * 0.28,
      blue: Math.random() > 0.6,
      ph: Math.random() * Math.PI * 2,
    });
  }

  var ot = 0;
  (function drawOv() {
    var W = overlay.width, H = overlay.height;
    oc.clearRect(0, 0, W, H);

    /* Slow blue horizontal bloom */
    var lineY = H * 0.5 + Math.sin(ot * 0.00025) * H * 0.07;
    var lg = oc.createLinearGradient(0, 0, W, 0);
    lg.addColorStop(0,   'transparent');
    lg.addColorStop(0.25,'rgba(65,151,250,0.03)');
    lg.addColorStop(0.5, 'rgba(65,151,250,0.055)');
    lg.addColorStop(0.75,'rgba(65,151,250,0.03)');
    lg.addColorStop(1,   'transparent');
    oc.fillStyle = lg;
    oc.fillRect(0, lineY - 90, W, 180);

    /* Particles + connections */
    for (var i = 0; i < N; i++) {
      var p = pts[i];
      p.x += p.vx;
      p.y += p.vy;
      if (p.x < -8)  p.x = W + 8;
      if (p.x > W+8) p.x = -8;
      if (p.y < -8)  p.y = H + 8;
      if (p.y > H+8) p.y = -8;

      var pa = p.a * (0.55 + 0.45 * Math.sin(ot * 0.0007 + p.ph));
      oc.beginPath();
      oc.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      oc.fillStyle = p.blue
        ? 'rgba(65,151,250,' + pa.toFixed(3) + ')'
        : 'rgba(255,255,255,' + (pa * 0.45).toFixed(3) + ')';
      oc.fill();

      for (var j = i + 1; j < N; j++) {
        var q = pts[j];
        var dx = p.x - q.x, dy = p.y - q.y;
        var d = Math.sqrt(dx*dx + dy*dy);
        if (d < 115) {
          var la = (1 - d / 115) * 0.045;
          oc.strokeStyle = p.blue
            ? 'rgba(65,151,250,' + la.toFixed(4) + ')'
            : 'rgba(255,255,255,' + (la * 0.4).toFixed(4) + ')';
          oc.lineWidth = 0.5;
          oc.beginPath();
          oc.moveTo(p.x, p.y);
          oc.lineTo(q.x, q.y);
          oc.stroke();
        }
      }
    }
    ot += 16;
    requestAnimationFrame(drawOv);
  })();

  /* ── 7. Patch navigateTo to re-run tilt + reveal on page switch ── */
  function patchNav() {
    if (typeof window.navigateTo !== 'function') {
      setTimeout(patchNav, 80);
      return;
    }
    /* avoid double-patching */
    if (window.navigateTo._fusePatch) return;
    var orig = window.navigateTo;
    window.navigateTo = function(target) {
      orig(target);
      setTimeout(function() {
        applyTilt('#page-store > div > div');
        attachReveal();
      }, 60);
    };
    window.navigateTo._fusePatch = true;
  }
  patchNav();

}

/* Run immediately if DOM ready, otherwise wait */
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', fuseInit);
} else {
  fuseInit();
}
