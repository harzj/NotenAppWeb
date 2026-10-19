/* Live-Vorschau im Browser – spiegelt app/grades/berechnung.py.
 * Gewichtete Mittel (KLN, mündliche Teilnoten) werden serverseitig berechnet
 * und als data-Attribute übergeben; hier wird nur noch mit Werten gerechnet,
 * die sich auf der Seite ändern können.
 */
window.Noten = (function () {
  'use strict';

  function roundNote15(x) {
    if (x === null || x === undefined || isNaN(x)) return null;
    return Math.max(0, Math.min(15, Math.round(x)));
  }

  // pairs: [[note, weight], ...]; null notes are skipped
  function weightedMean(pairs) {
    let sn = 0, sw = 0;
    pairs.forEach(([n, w]) => {
      if (n === null || n === undefined || isNaN(n)) return;
      sn += n * w; sw += w;
    });
    return sw > 0 ? sn / sw : null;
  }

  // SL-Note = (mdl·mdlPct + klnMean·klnPct) / (mdlPct + klnPct); a missing part drops out
  function slNote(mdl, klnMean, gw) {
    if (mdl === null && klnMean === null) return null;
    if (mdl === null) return klnMean;
    if (klnMean === null) return mdl;
    const mf = gw.sl_mdl_pct, kf = gw.sl_kln_pct, t = mf + kf;
    return t > 0 ? (mdl * mf + klnMean * kf) / t : null;
  }

  function parseNote(v) {
    if (v === '' || v === null || v === undefined) return null;
    const n = parseFloat(String(v).replace(',', '.'));
    return isNaN(n) ? null : n;
  }

  function fmt1(x) {
    return x === null ? '' : (Math.round(x * 10) / 10).toFixed(1).replace('.', ',');
  }

  function csrf() {
    return document.querySelector('meta[name=csrf-token]')?.content || '';
  }

  async function postJson(url, body) {
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
      body: JSON.stringify(body),
    });
    const d = await r.json().catch(() => ({}));
    return { ok: r.ok && !!d.ok, error: d.error };
  }

  function toast(msg, type) {
    const div = document.createElement('div');
    div.className = `toast align-items-center text-bg-${type} border-0 position-fixed bottom-0 end-0 m-3`;
    div.setAttribute('role', 'alert');
    const body = document.createElement('div');
    body.className = 'toast-body';
    body.textContent = msg;
    const wrap = document.createElement('div');
    wrap.className = 'd-flex';
    wrap.appendChild(body);
    wrap.insertAdjacentHTML('beforeend',
      '<button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>');
    div.appendChild(wrap);
    document.body.appendChild(div);
    new bootstrap.Toast(div, { delay: 3000 }).show();
    div.addEventListener('hidden.bs.toast', () => div.remove());
  }

  // Marks the page dirty on any input inside *root*; warns before leaving
  function trackDirty(root) {
    let dirty = false;
    root.addEventListener('input', e => { if (!e.target.closest('.modal')) dirty = true; });
    window.addEventListener('beforeunload', e => {
      if (dirty) { e.preventDefault(); e.returnValue = ''; }
    });
    return { isDirty: () => dirty, clear: () => { dirty = false; } };
  }

  return { roundNote15, weightedMean, slNote, parseNote, fmt1, postJson, toast, trackDirty };
})();
