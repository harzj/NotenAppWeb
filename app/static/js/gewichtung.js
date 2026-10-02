/* Gewichtungs-Eingaben (Seite „Notenberechnung“ und Gewichtungs-Modal).
 *
 * Jede .gw-group zeigt live, welchen Prozentanteil jedes Feld innerhalb der
 * Gruppe hat. „Übernehmen“ (.gw-save) sammelt alle .gw-field eines
 * .gw-container, speichert sie über /api/gewichtung/speichern und lädt die
 * Seite neu, damit alle Vorschläge serverseitig neu berechnet werden.
 * Hat die Seite ungespeicherte Eingaben (window.notenPage.isDirty()), werden
 * diese vorher über window.notenPage.save() gesichert.
 */
(function () {
  'use strict';

  function num(v) {
    const f = parseFloat(String(v).replace(',', '.'));
    return isNaN(f) ? null : f;
  }

  function updateGroup(group) {
    const fields = Array.from(group.querySelectorAll('.gw-field'));
    const total = fields.reduce((s, f) => s + Math.max(0, num(f.value) || 0), 0);
    fields.forEach(f => {
      const pct = f.closest('.gw-item')?.querySelector('.gw-pct');
      if (!pct) return;
      const v = num(f.value);
      pct.textContent = (total > 0 && v !== null) ? (Math.round(1000 * v / total) / 10).toLocaleString('de-DE') + ' %' : '–';
    });
  }

  function collect(container) {
    const payload = { gewichtung: {} };
    container.querySelectorAll('.gw-field').forEach(f => {
      const v = num(f.value);
      if (v === null) return;
      if (f.dataset.kind === 'g') {
        payload.gewichtung[f.dataset.key] = v;
      } else {
        const store = (payload[f.dataset.store] = payload[f.dataset.store] || {});
        (store[f.dataset.slot] = store[f.dataset.slot] || {})[f.dataset.sheet] = v;
      }
    });
    return payload;
  }

  async function save(container, btn) {
    const err = container.querySelector('.gw-error') ||
                btn.closest('.modal-content')?.querySelector('.gw-error');
    if (err) err.textContent = '';
    btn.disabled = true;
    try {
      const page = window.notenPage;
      if (page && typeof page.isDirty === 'function' && page.isDirty() && typeof page.save === 'function') {
        const ok = await page.save();
        if (ok === false) throw new Error('Die Noten auf dieser Seite konnten nicht gespeichert werden.');
      }
      const r = await fetch('/api/gewichtung/speichern', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json',
                   'X-CSRFToken': document.querySelector('meta[name=csrf-token]')?.content || '' },
        body: JSON.stringify(collect(container)),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok || !d.ok) throw new Error(d.error || 'Fehler beim Speichern der Gewichtung.');
      window.location.reload();
    } catch (e) {
      if (err) err.textContent = e.message; else alert(e.message);
      btn.disabled = false;
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.gw-group').forEach(g => {
      updateGroup(g);
      g.addEventListener('input', () => updateGroup(g));
    });
    document.querySelectorAll('.gw-save').forEach(btn => {
      const container = btn.closest('.gw-container') ||
                        btn.closest('.modal-content')?.querySelector('.gw-container');
      if (container) btn.addEventListener('click', () => save(container, btn));
    });
  });
})();
