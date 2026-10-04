/* Repliage des groupes imbriqués des listes, et chargement de leurs lignes.
 *
 * Les en-têtes de groupe sont tous dans la page — ils sont légers. Les lignes de
 * données, non : les charger d'avance mettait dans le HTML, repliées et souvent
 * jamais lues, toutes les lignes de tous les groupes affichés. Une ligne pèse
 * plus d'un kilo-octet ; un regroupement à gros groupes produisait une page de
 * plusieurs dizaines de méga-octets pour un écran qui ne montrait que des
 * en-têtes.
 *
 * Déplier un groupe feuille va donc chercher ses lignes au serveur, **une seule
 * fois** : une fois dans la page elles y restent, et replier puis redéplier
 * redevient instantané. La page est redemandée avec `_groupe=<chemin>` ; le
 * serveur ne renvoie alors que les lignes du groupe (core.listing.reponse_du_groupe).
 *
 * Un gros groupe arrive par lots : le serveur termine chaque lot par une entrée
 * « Charger plus » (`lst-plus`) qui porte le rang du suivant (`data-suite`).
 *
 * Volontairement sans en-tête `X-Requested-With` : plusieurs listes répondent
 * alors par un fragment, et un `<tr>` hors d'un `<table>` est purement et
 * simplement jeté par l'analyseur HTML.
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

  function urlDuGroupe(chemin, decalage) {
    var params = new URLSearchParams(location.search);
    params.set('_groupe', chemin);
    if (decalage) params.set('_decalage', decalage);
    else params.delete('_decalage');
    return location.pathname + '?' + params.toString();
  }

  /* Va chercher un lot de lignes du groupe et les insère après `ancre`.
   *
   * `declencheur` est l'élément cliqué — l'en-tête au premier dépliage, l'entrée
   * « Charger plus » ensuite — et porte le signe de chargement. */
  function charger(declencheur, ancre, chemin, decalage) {
    declencheur.classList.add('lst-chargement');
    return fetch(urlDuGroupe(chemin, decalage), { credentials: 'same-origin' })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.text();
      })
      .then(function (html) {
        var doc = new DOMParser().parseFromString(html, 'text/html');
        // La réponse porte les lignes de tableau et, pour les listes à kanban,
        // les fiches : chacun ne prend que celles de sa propre vue.
        var enTableau = declencheur.tagName === 'TR';
        // L'entrée « Charger plus » s'étale sur toute la largeur du tableau,
        // que seule la page connaît : on reprend celle de la cellule cliquée.
        var largeur = enTableau ? declencheur.cells[0].colSpan : 0;
        doc.querySelectorAll('[data-parent="' + chemin + '"]').forEach(function (el) {
          if ((el.tagName === 'TR') !== enTableau) return;
          // importNode : le nœud vient d'un autre document.
          var copie = document.importNode(el, true);
          copie.style.display = '';
          if (enTableau && copie.classList.contains('lst-plus')) {
            copie.cells[0].colSpan = largeur;
          }
          ancre.insertAdjacentElement('afterend', copie);
          ancre = copie;
        });
        return true;
      })
      .catch(function () {
        if (window.showToast) {
          showToast("Impossible de charger les lignes de ce groupe.", 'error');
        }
        return false;
      })
      .finally(function () { declencheur.classList.remove('lst-chargement'); });
  }

  /* Lot suivant d'un gros groupe : inséré à la place de l'entrée cliquée. */
  function chargerPlus(plus) {
    if (plus.classList.contains('lst-chargement')) return;   // déjà en vol
    charger(plus, plus, plus.dataset.parent, plus.dataset.suite).then(function (ok) {
      if (ok) plus.remove();
    });
  }

  function ouvrir(entete, chemin) {
    entete.classList.add('open');
    enfantsDirects(chemin).forEach(function (el) { el.style.display = ''; });
  }

  function basculer(ligne) {
    var chemin = ligne.dataset.chemin;

    if (!ligne.classList.contains('open')) {
      // Un groupe feuille jamais ouvert n'a pas encore ses lignes.
      if (ligne.dataset.feuille === '1' && ligne.dataset.charge !== '1') {
        if (ligne.classList.contains('lst-chargement')) return;   // déjà en vol
        charger(ligne, ligne, chemin, 0).then(function (ok) {
          if (!ok) return;
          ligne.dataset.charge = '1';
          ouvrir(ligne, chemin);
        });
        return;
      }
      ouvrir(ligne, chemin);
      return;
    }

    // Fermeture : on cache enfants et descendance, et on referme les sous-groupes.
    ligne.classList.remove('open');
    enfantsDirects(chemin).forEach(function (el) { el.style.display = 'none'; });
    descendance(chemin).forEach(function (el) { el.style.display = 'none'; });
    document.querySelectorAll('.lst-groupe[data-chemin^="' + chemin + '-"]')
      .forEach(function (el) { el.classList.remove('open'); });
  }

  window.lstBasculerGroupe = basculer;
  window.lstChargerPlus = chargerPlus;
})();
