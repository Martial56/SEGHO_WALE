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
 * La page est demandée en AJAX : les listes qui savent rendre un fragment en
 * rendent un, et c'est quatre fois plus rapide — 146 ms et 44 Ko au lieu de
 * 554 ms et 256 Ko, mesuré sur les rendez-vous, pour en tirer trois lignes.
 * Celles qui n'en rendent pas renvoient la page entière, ce qui marche aussi.
 *
 * Un fragment fait de `<tr>` nus serait jeté par l'analyseur HTML, qui ne garde
 * une ligne que dans un tableau. Aucune liste n'est dans ce cas aujourd'hui,
 * mais `lignesDu` réessaie dans un `<table>` plutôt que de rendre une page vide
 * le jour où l'une d'elles le deviendrait.
 *
 * Chaque ligne porte `data-parent`, le chemin de son groupe parent. Déplier un
 * groupe montre ses enfants directs ; le replier cache toute sa descendance et
 * remet ses sous-groupes à l'état fermé, pour qu'un nouveau dépliage reparte
 * d'un état prévisible.
 *
 * ── Tout se cherche dans un seul conteneur ──
 *
 * Patients et gynécologie rendent **deux** vues du même regroupement dans la
 * même page : des fiches dans `#kanban-view`, des lignes dans `#list-view`. Les
 * deux portent les mêmes `data-chemin` et les mêmes `data-parent`, puisque
 * c'est le même arbre. Chercher dans `document` ne pouvait donc pas les
 * distinguer : déplier une bande du kanban y versait les 199 fiches **et** les
 * 199 `<tr>` du tableau, que la grille étirait à 3000 px de large — d'où les
 * colonnes démesurées et le défilement horizontal. Le tableau recevait
 * symétriquement les fiches.
 *
 * Tout part donc du conteneur de l'en-tête cliqué (`parentElement` : la grille
 * ou le `<tbody>`), y compris côté réponse, où l'on repère la bande jumelle à sa
 * balise — un `<div>` pour le kanban, un `<tr>` pour le tableau — avant d'y
 * prendre ses lignes. Chaque vue charge ainsi les siennes, et une seule fois.
 */
(function () {
  'use strict';

  function enfantsDirects(racine, chemin) {
    return racine.querySelectorAll('[data-parent="' + chemin + '"]');
  }

  function descendance(racine, chemin) {
    // Le préfixe suivi d'un tiret évite de confondre « 1 » avec « 11 ».
    return racine.querySelectorAll('[data-parent^="' + chemin + '-"]');
  }

  function urlDuGroupe(chemin) {
    var params = new URLSearchParams(location.search);
    params.set('_groupe', chemin);
    return location.pathname + '?' + params.toString();
  }

  /* Le conteneur, dans la réponse, qui correspond à celui de l'en-tête cliqué.
   *
   * La bande jumelle est celle qui porte le même chemin et la même balise ; son
   * parent est la vue d'où il faut prendre les lignes. Nul si la réponse ne rend
   * pas cette vue — on le dit à l'appelant plutôt que de deviner.
   */
  function conteneurJumeau(doc, chemin, entete) {
    var jumelles = doc.querySelectorAll('[data-chemin="' + chemin + '"]');
    for (var i = 0; i < jumelles.length; i++) {
      if (jumelles[i].tagName === entete.tagName) return jumelles[i].parentElement;
    }
    return null;
  }

  /* Les lignes du groupe dans la réponse, prises dans la bonne vue. */
  function lignesDu(html, chemin, entete) {
    var selecteur = '[data-parent="' + chemin + '"]';
    var doc = new DOMParser().parseFromString(html, 'text/html');
    var conteneur = conteneurJumeau(doc, chemin, entete);
    if (conteneur) return conteneur.querySelectorAll(selecteur);

    // Pas de bande jumelle — une réponse qui ne rendrait que les lignes. Rien à
    // cloisonner dans ce cas : on prend ce qu'il y a, comme avant.
    var trouvees = doc.querySelectorAll(selecteur);
    if (trouvees.length) return trouvees;

    // Toujours rien : peut-être un fragment de `<tr>` nus, que l'analyseur
    // jette hors d'un tableau. On lui en donne un.
    doc = new DOMParser()
      .parseFromString('<table><tbody>' + html + '</tbody></table>', 'text/html');
    conteneur = conteneurJumeau(doc, chemin, entete);
    return (conteneur || doc).querySelectorAll(selecteur);
  }

  /* Va chercher les lignes du groupe et les insère après son en-tête. */
  function charger(entete, chemin) {
    entete.classList.add('lst-chargement');
    return fetch(urlDuGroupe(chemin), {
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest' }
    })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.text();
      })
      .then(function (html) {
        var ancre = entete;
        lignesDu(html, chemin, entete).forEach(function (el) {
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
    enfantsDirects(entete.parentElement, chemin)
      .forEach(function (el) { el.style.display = ''; });
  }

  function basculer(ligne) {
    var chemin = ligne.dataset.chemin;
    var racine = ligne.parentElement;

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
    enfantsDirects(racine, chemin).forEach(function (el) { el.style.display = 'none'; });
    descendance(racine, chemin).forEach(function (el) { el.style.display = 'none'; });
    racine.querySelectorAll('.lst-groupe[data-chemin^="' + chemin + '-"]')
      .forEach(function (el) { el.classList.remove('open'); });
  }

  window.lstBasculerGroupe = basculer;
})();
