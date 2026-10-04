/* Revenir à une liste sans la refabriquer.
 *
 * Le bouton « Retour » d'une fiche pointe vers la liste nue — « /patients/ »,
 * « /patients/rendez-vous/ ». C'est une navigation en avant : le navigateur
 * construit une page neuve, et le serveur doit lui réapprendre d'où l'on vient
 * (core.memoire_listing). Tout revient, mais tout est refait.
 *
 * Or la page qu'on veut est encore là, intacte, dans l'historique. Quand le lien
 * mène exactement là d'où l'on vient, reculer vaut donc mieux que le suivre : le
 * navigateur ressort la page telle qu'on l'avait laissée — groupes dépliés,
 * position de défilement, panneaux ouverts — sans une seule requête.
 *
 * ── Pourquoi comparer au référent ──
 *
 * On ne remplace le lien que lorsque reculer mène au même endroit qu'avancer :
 * c'est ce qui rend l'échange sûr. Décider au nom du bouton (« Retour »,
 * « Ignorer ») aurait fait reculer depuis des pages où l'on n'était jamais
 * passé. Sont donc écartés :
 *
 * * les liens qui demandent autre chose que ce d'où l'on vient — une autre
 *   adresse, d'autres critères, une ancre ;
 * * les pages qui ont elles-mêmes bougé dans l'historique : la fiche patient
 *   change d'URL en changeant d'onglet (pushState), et un cran en arrière y
 *   ramènerait à l'onglet précédent, pas à la liste ;
 * * l'ouverture dans un onglet neuf, qui n'a pas d'historique derrière elle.
 *
 * ── Ce que coûte un retour ──
 *
 * Rien, quand le navigateur garde la page en mémoire (bfcache) : elle revient
 * telle quelle, sans toucher au réseau. Sinon il redemande l'URL précédente —
 * celle qui porte l'état déplié —, et la page arrive dans le bon état du premier
 * coup, là où le lien, qui ne sait rien de ce qui était ouvert, part de la liste
 * nue et fait tout refaire au serveur.
 *
 * Le bfcache ne se commande pas : le navigateur décide, et il refuse pour des
 * raisons qui lui appartiennent — un simple aller-retour dans Chrome sans
 * fenêtre s'est vu refuser pour « BrowsingInstanceNotSwapped ». Rien ici n'en
 * dépend donc : on y gagne quand il joue, et on ne perd rien quand il ne joue
 * pas.
 */
(function () {
  'use strict';

  /* L'adresse du premier affichage. Les pages qui se réécrivent en naviguant
   * dans leurs onglets s'en éloignent, et c'est à cela qu'on les reconnaît. */
  var urlInitiale = location.href;

  function analyser(url) {
    try { return new URL(url, location.href); } catch (e) { return null; }
  }

  function clicSimple(e) {
    return !e.defaultPrevented && e.button === 0 &&
           !e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey;
  }

  document.addEventListener('click', function (e) {
    if (!clicSimple(e) || !e.target.closest) return;
    var a = e.target.closest('a[href]');
    if (!a || a.target || a.hasAttribute('download')) return;

    if (history.length <= 1 || !document.referrer) return;
    if (location.href !== urlInitiale) return;

    var vise = analyser(a.getAttribute('href'));
    var venu = analyser(document.referrer);
    if (!vise || !venu || venu.origin !== location.origin) return;
    if (vise.hash) return;

    // Reculer doit mener exactement là où le lien mène, sans quoi on détourne
    // le clic vers une page que personne n'a demandée.
    if (vise.pathname !== venu.pathname) return;
    // Et pas vers la page courante : ce serait un lien interne, pas un retour.
    if (vise.pathname === location.pathname) return;
    // Des critères que le référent n'avait pas : le lien demande autre chose.
    if (vise.search && vise.search !== venu.search) return;

    e.preventDefault();
    history.back();
  });
})();
