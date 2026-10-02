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
 * redevient instantané. La page est redemandée avec `_groupe=<chemin>` et on n'y
 * prend que les lignes du groupe, comme rafraichir() ne prend que les zones qui
 * l'intéressent.
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

  function urlDuGroupe(chemin) {
    var params = new URLSearchParams(location.search);
    params.set('_groupe', chemin);
    return location.pathname + '?' + params.toString();
  }

  /* Va chercher les lignes du groupe et les insère après son en-tête. */
  function charger(entete, chemin) {
    entete.classList.add('lst-chargement');
    return fetch(urlDuGroupe(chemin), { credentials: 'same-origin' })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.text();
      })
      .then(function (html) {
        var doc = new DOMParser().parseFromString(html, 'text/html');
        var ancre = entete;
        doc.querySelectorAll('[data-parent="' + chemin + '"]').forEach(function (el) {
          // importNode : le nœud vient d'un autre document.
          var copie = document.importNode(el, true);
          copie.style.display = '';
          ancre.insertAdjacentElement('afterend', copie);
          ancre = copie;
        });
        entete.dataset.charge = '1';
      })
      .catch(function () {
        if (window.showToast) {
          showToast("Impossible d'ouvrir ce groupe.", 'error');
        }
      })
      .finally(function () { entete.classList.remove('lst-chargement'); });
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
        charger(ligne, chemin).then(function () {
          if (ligne.dataset.charge === '1') ouvrir(ligne, chemin);
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
})();
