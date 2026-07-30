/* Repliage des groupes imbriqués des listes.
 *
 * Entièrement côté navigateur : toutes les lignes des groupes affichés sont déjà
 * dans la page (la pagination porte sur les groupes, pas sur les lignes), donc
 * déplier n'appelle jamais le serveur et ne provoque aucune attente.
 *
 * Chaque ligne porte `data-parent`, le chemin de son groupe parent. Déplier un
 * groupe montre ses enfants directs ; le replier cache toute sa descendance et
 * remet ses sous-groupes à l'état fermé, pour qu'un nouveau dépliage reparte
 * d'un état prévisible.
 */
(function () {
  'use strict';

  function enfantsDirects(chemin) {
    return document.querySelectorAll('[data-parent="' + chemin + '"]');
  }

  function descendance(chemin) {
    // Le préfixe suivi d'un tiret évite de confondre « 1 » avec « 11 ».
    return document.querySelectorAll('[data-parent^="' + chemin + '-"]');
  }

  function basculer(ligne) {
    var chemin = ligne.dataset.chemin;
    var ouvrir = !ligne.classList.contains('open');
    ligne.classList.toggle('open', ouvrir);

    if (ouvrir) {
      enfantsDirects(chemin).forEach(function (el) { el.style.display = ''; });
      return;
    }
    // Fermeture : on cache enfants et descendance, et on referme les sous-groupes.
    enfantsDirects(chemin).forEach(function (el) { el.style.display = 'none'; });
    descendance(chemin).forEach(function (el) { el.style.display = 'none'; });
    document.querySelectorAll('.lst-groupe[data-chemin^="' + chemin + '-"]')
      .forEach(function (el) { el.classList.remove('open'); });
  }

  window.lstBasculerGroupe = basculer;
})();
