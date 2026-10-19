/* Onboarding: Seiten-Rundgänge (driver.js) und Checkliste „Erste Schritte“.
 *
 * Datenschutz: Es wird nichts an den Server geschickt. Ob ein Rundgang schon
 * gesehen wurde oder ein Checklisten-Punkt erledigt ist, steht nur im
 * localStorage dieses Browsers (jeder Zugriff abgesichert, falls blockiert).
 *
 * Eine Seite definiert ihren Rundgang als JSON in <script id="pageTour">:
 *   {"id": "sl", "steps": [{"el": "[data-tour=formel]", "title": "…", "text": "…", "side": "bottom"}]}
 * Schritte ohne "el" erscheinen mittig. Schritte, deren Element fehlt oder
 * unsichtbar ist, werden übersprungen.
 *
 * data-check-visit="key"  → Checklisten-Punkt beim Besuch der Seite erledigt
 * data-check-click="key"  → Checklisten-Punkt beim Klick auf das Element erledigt
 */
(function () {
  'use strict';

  const PREFIX = 'notenapp.';
  const store = {
    get(k) { try { return window.localStorage.getItem(PREFIX + k); } catch (e) { return null; } },
    set(k, v) { try { window.localStorage.setItem(PREFIX + k, v); } catch (e) { /* ignore */ } },
    del(k) { try { window.localStorage.removeItem(PREFIX + k); } catch (e) { /* ignore */ } },
  };

  function readTour() {
    const el = document.getElementById('pageTour');
    if (!el) return null;
    try {
      const t = JSON.parse(el.textContent || 'null');
      return t && Array.isArray(t.steps) && t.steps.length ? t : null;
    } catch (e) { return null; }
  }

  function visible(el) {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden';
  }

  function buildSteps(tour) {
    const steps = [];
    tour.steps.forEach(s => {
      const pop = { title: s.title || '', description: s.text || '', side: s.side || 'bottom', align: s.align || 'start' };
      if (!s.el) { steps.push({ popover: pop }); return; }
      const el = document.querySelector(s.el);
      if (visible(el)) steps.push({ element: el, popover: pop });
    });
    return steps;
  }

  function startTour(tour) {
    tour = tour || readTour();
    const factory = window.driver && window.driver.js && window.driver.js.driver;
    if (!tour || !factory) return false;
    const steps = buildSteps(tour);
    if (!steps.length) return false;
    store.set('tour.' + tour.id, 'seen');
    hideOffer();
    factory({
      showProgress: steps.length > 1,
      progressText: '{{current}} von {{total}}',
      nextBtnText: 'Weiter',
      prevBtnText: 'Zurück',
      doneBtnText: 'Fertig',
      overlayOpacity: 0.55,
      smoothScroll: true,
      steps,
    }).drive();
    return true;
  }

  // ── Dezentes Angebot beim ersten Besuch einer Seite ──────────────────────────
  function hideOffer() {
    document.getElementById('tourOffer')?.remove();
  }

  function offerTour(tour) {
    if (store.get('tour.off') || store.get('tour.' + tour.id)) return;
    if (!buildSteps(tour).length) return;
    const box = document.createElement('div');
    box.id = 'tourOffer';
    box.className = 'card shadow position-fixed bottom-0 end-0 m-3';
    box.style.cssText = 'z-index:1060;max-width:320px';
    box.innerHTML =
      '<div class="card-body p-3">' +
      '<div class="fw-semibold mb-1"><i class="bi bi-signpost-split me-1 text-primary"></i>Kurze Einführung?</div>' +
      '<div class="small text-muted mb-2">Ein Rundgang zeigt in einer Minute, was es auf dieser Seite gibt. ' +
      'Später jederzeit über <i class="bi bi-question-circle"></i> Hilfe oben rechts.</div>' +
      '<div class="d-flex gap-2 flex-wrap">' +
      '<button type="button" class="btn btn-sm btn-primary" data-act="start">Rundgang starten</button>' +
      '<button type="button" class="btn btn-sm btn-outline-secondary" data-act="later">Nein danke</button>' +
      '</div>' +
      '<button type="button" class="btn btn-link btn-sm p-0 mt-2 small text-muted" data-act="off">Keine Rundgänge mehr anbieten</button>' +
      '</div>';
    box.addEventListener('click', e => {
      const act = e.target.closest('[data-act]')?.dataset.act;
      if (act === 'start') startTour(tour);
      else if (act === 'later') { store.set('tour.' + tour.id, 'dismissed'); hideOffer(); }
      else if (act === 'off') { store.set('tour.off', '1'); hideOffer(); }
    });
    document.body.appendChild(box);
  }

  // ── Checkliste „Erste Schritte“ ──────────────────────────────────────────────
  function markDone(key) { if (key) store.set('check.' + key, '1'); }

  function renderChecklist() {
    const card = document.getElementById('ersteSchritte');
    const reopen = document.getElementById('ersteSchritteZeigen');
    if (!card) return;
    const hidden = !!store.get('checklist.hidden');
    card.classList.toggle('d-none', hidden);
    reopen?.classList.toggle('d-none', !hidden);

    let done = 0, total = 0;
    card.querySelectorAll('[data-step]').forEach(li => {
      const isDone = li.dataset.done === '1' || (li.dataset.checkKey && store.get('check.' + li.dataset.checkKey));
      li.classList.toggle('erledigt', !!isDone);
      const icon = li.querySelector('.step-icon');
      if (icon) icon.className = 'step-icon bi ' + (isDone ? 'bi-check-circle-fill text-success' : 'bi-circle text-muted');
      if (!li.hasAttribute('data-optional')) { total += 1; if (isDone) done += 1; }
    });
    const bar = card.querySelector('.progress-bar');
    if (bar) bar.style.width = (total ? Math.round(100 * done / total) : 0) + '%';
    const cnt = card.querySelector('.steps-count');
    if (cnt) cnt.textContent = `${done} von ${total} erledigt`;
  }

  function bindChecklist() {
    document.querySelector('#ersteSchritte [data-act=hide]')?.addEventListener('click', () => {
      store.set('checklist.hidden', '1'); renderChecklist();
    });
    document.getElementById('ersteSchritteZeigen')?.addEventListener('click', e => {
      e.preventDefault(); store.del('checklist.hidden'); renderChecklist();
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-check-visit]').forEach(el => markDone(el.dataset.checkVisit));
    document.querySelectorAll('[data-check-click]').forEach(el =>
      el.addEventListener('click', () => markDone(el.dataset.checkClick)));
    bindChecklist();
    renderChecklist();

    document.querySelectorAll('[data-start-tour]').forEach(btn => btn.addEventListener('click', e => {
      e.preventDefault();
      if (!startTour()) {
        alert('Für diese Seite gibt es keinen Rundgang. Auf der Startseite findest du die Checkliste „Erste Schritte“.');
      }
    }));
    // data-reset-tours: offer all tours again; ="full" also resets the checklist and
    // follows the link (e.g. to the start page, where the tour is offered right away)
    document.querySelectorAll('[data-reset-tours]').forEach(btn => btn.addEventListener('click', e => {
      e.preventDefault();
      const full = btn.dataset.resetTours === 'full';
      try {
        Object.keys(window.localStorage)
          .filter(k => k.startsWith(PREFIX + 'tour.') || k === PREFIX + 'checklist.hidden' ||
                       (full && k.startsWith(PREFIX + 'check.')))
          .forEach(k => window.localStorage.removeItem(k));
      } catch (err) { /* ignore */ }
      const href = btn.getAttribute('href');
      if (full && href && href !== '#') window.location.href = href;
      else window.location.reload();
    }));

    const tour = readTour();
    // Don't stack the offer on top of an open modal or a fresh flash message flood
    if (tour) setTimeout(() => { if (!document.querySelector('.modal.show')) offerTour(tour); }, 600);
  });

  window.NotenOnboarding = { startTour, markDone };
})();
