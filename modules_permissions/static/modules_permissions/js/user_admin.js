/**
 * user_admin.js
 * Dans le formulaire UserAdmin de Django :
 * - Quand les groupes sélectionnés changent, appelle l'API /admin/auth/user/modules-par-groupe/
 * - Affiche un panneau listant les modules disponibles pour ces groupes
 */
(function () {
  'use strict';

  // Attend que le DOM soit prêt
  document.addEventListener('DOMContentLoaded', function () {
    // Trouver le select des groupes (filter_horizontal génère deux selects)
    // Le select source a l'id "id_groups_from", le select cible "id_groups_to"
    // On écoute aussi le select simple au cas où filter_horizontal ne serait pas actif
    var groupsTo = document.getElementById('id_groups_to');
    var groupsSimple = document.getElementById('id_groups');

    // Créer le panneau de prévisualisation
    var panel = createPanel();

    // Insérer le panneau après le champ groups (chercher le fieldset Permissions)
    var groupsField = (groupsTo || groupsSimple);
    if (!groupsField) return;

    var container = groupsField.closest('.form-row') || groupsField.closest('p') || groupsField.parentNode;
    if (container && container.parentNode) {
      container.parentNode.insertBefore(panel, container.nextSibling);
    }

    // Mettre à jour lors de la sélection
    function onGroupChange() {
      var ids = getSelectedGroupIds();
      updateModulesPanel(ids);
    }

    // Écouter les deux selects
    if (groupsTo) {
      // filter_horizontal : écouter les boutons ajouter/retirer
      groupsTo.addEventListener('change', onGroupChange);
      // Les boutons du widget filter_horizontal envoient des DOMSubtreeModified
      // mais mieux vaut observer via MutationObserver
      var observer = new MutationObserver(onGroupChange);
      observer.observe(groupsTo, { childList: true });
    }
    if (groupsSimple) {
      groupsSimple.addEventListener('change', onGroupChange);
    }

    // Mise à jour initiale
    onGroupChange();
  });

  function getSelectedGroupIds() {
    var ids = [];
    // Select cible du widget filter_horizontal
    var sel = document.getElementById('id_groups_to') || document.getElementById('id_groups');
    if (!sel) return ids;
    for (var i = 0; i < sel.options.length; i++) {
      if (sel.options[i].value) {
        ids.push(sel.options[i].value);
      }
    }
    return ids;
  }

  function createPanel() {
    var div = document.createElement('div');
    div.id = 'modules-preview-panel';
    div.innerHTML = '<h3>🗂️ Modules accessibles selon le(s) groupe(s) sélectionné(s)</h3>' +
      '<div class="modules-badges"><span id="modules-empty" style="color:#888;font-style:italic">Sélectionnez un groupe pour voir ses modules…</span></div>';
    return div;
  }

  function updateModulesPanel(groupIds) {
    var badgesContainer = document.querySelector('#modules-preview-panel .modules-badges');
    if (!badgesContainer) return;

    if (!groupIds || groupIds.length === 0) {
      badgesContainer.innerHTML = '<span id="modules-empty" style="color:#888;font-style:italic">Sélectionnez un groupe pour voir ses modules…</span>';
      return;
    }

    badgesContainer.innerHTML = '<span style="color:#aaa;font-style:italic">Chargement…</span>';

    var url = '/admin/auth/user/modules-par-groupe/?group_ids=' + groupIds.join('&group_ids=');

    fetch(url, { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var modules = data.modules || [];
        if (modules.length === 0) {
          badgesContainer.innerHTML = '<span style="color:#c0392b;font-style:italic">⚠️ Aucun module configuré pour ce(s) groupe(s).</span>';
          return;
        }
        badgesContainer.innerHTML = modules.map(function (m) {
          return '<span class="module-badge">' +
            m.icon + ' ' + m.name +
            ' <span class="badge-group">(' + m.group + ')</span>' +
            '</span>';
        }).join('');
      })
      .catch(function () {
        badgesContainer.innerHTML = '<span style="color:#c0392b">Erreur de chargement des modules.</span>';
      });
  }
})();
