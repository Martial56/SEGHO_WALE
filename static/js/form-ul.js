/* ══════════════════════════════════════════════════════════════
   COMPORTEMENTS PARTAGÉS — système de formulaire "field-ul"
   Onglets génériques + aperçu photo. Chargé globalement.
   ══════════════════════════════════════════════════════════════ */
(function () {
    /* ── Onglets (.tabs-nav > .tab-btn[data-tab] + #tab-<name>.tab-panel) ── */
    document.addEventListener('click', function (e) {
        var btn = e.target.closest('.tab-btn[data-tab]');
        if (!btn) return;
        var wrapper = btn.closest('.tabs-wrapper') || document;
        wrapper.querySelectorAll('.tab-btn').forEach(function (b) { b.classList.remove('active'); });
        wrapper.querySelectorAll('.tab-panel').forEach(function (p) { p.classList.remove('active'); });
        btn.classList.add('active');
        var panel = wrapper.querySelector('#tab-' + btn.dataset.tab);
        if (panel) panel.classList.add('active');
    });

    /* ── Aperçu photo générique ──
       <input type="file" data-photo-input="X"> + <img data-photo-preview="X">
       + <div data-photo-placeholder="X"> (optionnel) + <div data-photo-overlay="X"> (optionnel) */
    document.querySelectorAll('[data-photo-input]').forEach(function (input) {
        var previewSel = input.getAttribute('data-photo-input');
        var preview = document.querySelector('[data-photo-preview="' + previewSel + '"]');
        var placeholder = document.querySelector('[data-photo-placeholder="' + previewSel + '"]');
        var overlay = document.querySelector('[data-photo-overlay="' + previewSel + '"]');
        input.addEventListener('change', function () {
            var file = this.files[0];
            if (!file) return;
            var reader = new FileReader();
            reader.onload = function (e) {
                if (placeholder) placeholder.style.display = 'none';
                if (preview) { preview.src = e.target.result; preview.style.display = 'block'; }
                if (overlay) overlay.style.display = 'flex';
            };
            reader.readAsDataURL(file);
        });
    });
})();
