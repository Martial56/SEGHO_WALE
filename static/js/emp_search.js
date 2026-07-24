/* Widget de recherche employé partagé (form.html, historique_recherche.html).
   Filtre EMPLOYES_LIST par nom/matricule/service, gère le dropdown et la navigation clavier. */
function initEmpSearch(opts) {
  var input    = document.getElementById(opts.inputId);
  var dropdown = document.getElementById(opts.dropdownId);
  var employes = opts.employes;
  var onSelect = opts.onSelect;
  var focusIdx = -1;

  function renderDropdown(items) {
    if (!items.length) {
      dropdown.innerHTML = '<div class="emp-no-result"><i class="bi bi-search"></i> Aucun résultat</div>';
    } else {
      dropdown.innerHTML = items.slice(0, 12).map(function(e, i) {
        return '<div class="emp-dropdown-item" data-pk="' + e.pk + '" data-idx="' + i + '">' +
          '<div><div class="emp-di-name">' + e.nom + '</div>' +
          '<div class="emp-di-sub">' + (e.svc || '—') + (e.fn ? ' · ' + e.fn : '') + '</div></div>' +
          '<span class="emp-di-mat">' + e.mat + '</span></div>';
      }).join('');
      dropdown.querySelectorAll('.emp-dropdown-item').forEach(function(item) {
        item.addEventListener('mousedown', function(ev) {
          ev.preventDefault();
          onSelect(parseInt(this.dataset.pk));
        });
      });
    }
    dropdown.style.display = 'block';
    focusIdx = -1;
  }

  function filtrer(q) {
    q = q.trim().toLowerCase();
    return employes.filter(function(e) {
      return e.nom.toLowerCase().includes(q) ||
             e.mat.toLowerCase().includes(q) ||
             (e.svc || '').toLowerCase().includes(q);
    });
  }

  input.addEventListener('input', function() {
    var q = this.value;
    if (!q.trim()) { dropdown.style.display = 'none'; if (opts.onClear) opts.onClear(); return; }
    renderDropdown(filtrer(q));
  });

  input.addEventListener('keydown', function(e) {
    var items = dropdown.querySelectorAll('.emp-dropdown-item');
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      focusIdx = Math.min(focusIdx + 1, items.length - 1);
      items.forEach(function(el, i) { el.classList.toggle('focused', i === focusIdx); });
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      focusIdx = Math.max(focusIdx - 1, 0);
      items.forEach(function(el, i) { el.classList.toggle('focused', i === focusIdx); });
    } else if (e.key === 'Enter' && focusIdx >= 0 && items[focusIdx]) {
      e.preventDefault();
      onSelect(parseInt(items[focusIdx].dataset.pk));
    } else if (e.key === 'Escape') {
      dropdown.style.display = 'none';
    }
  });

  if (opts.onFocus !== false) {
    input.addEventListener('focus', function() {
      if (this.value && (!opts.hasSelection || !opts.hasSelection())) {
        renderDropdown(filtrer(this.value));
      }
    });
  }

  document.addEventListener('click', function(e) {
    if (!e.target.closest('.emp-search-wrap')) dropdown.style.display = 'none';
  });

  return { renderDropdown: renderDropdown, filtrer: filtrer };
}
