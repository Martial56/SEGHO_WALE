/* Repliage des groupes imbriqués des listes, et chargement de leurs lignes.
 *
 * Les en-têtes de groupe sont tous dans la page — ils sont légers. Les lignes de
 * données, non : les mettre dans le HTML d'entrée y plaçait, repliées et souvent
 * jamais lues, toutes les lignes de tous les groupes affichés. Une ligne pèse
 * plus d'un kilo-octet ; un regroupement à gros groupes produisait une page de
 * plusieurs dizaines de méga-octets pour un écran qui ne montrait que des
 * en-têtes, et il avait fallu descendre à huit groupes par page pour tenir.
 *
 * ── Ce qui arrive quand ──
 *
 * La page part donc avec ses seuls en-têtes, et s'affiche aussitôt. Puis, une
 * fois à l'écran, le navigateur va chercher **en une seule requête** les lignes
 * de tous les groupes de la page et les range, repliées, sous leurs bandes.
 * Pendant qu'on lit les en-têtes, tout arrive ; déplier ne fait plus attendre.
 *
 * C'est le dépliage instantané d'avant le chargement différé, sans sa page de
 * plusieurs méga-octets : le volume est le même, mais il vient après coup et ne
 * retarde rien. Vingt-cinq groupes par page, et non huit.
 *
 * Déplier un groupe que le préchargement n'a pas encore atteint — ou qu'il a
 * renoncé à prendre, voir MAX_LIGNES_PRECHARGEES — va chercher ses lignes à
 * lui, comme avant. Dans les deux cas c'est **une seule fois** : une fois dans
 * la page les lignes y restent, et replier puis redéplier est instantané.
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
 * Tout part donc du conteneur de l'en-tête visé (`parentElement` : la grille ou
 * le `<tbody>`), y compris côté réponse, où l'on repère la bande jumelle à sa
 * balise — un `<div>` pour le kanban, un `<tr>` pour le tableau — avant d'y
 * prendre ses lignes. Chaque vue a ainsi les siennes, et basculer de l'une à
 * l'autre reste instantané.
 */
(function () {
  'use strict';

  /* Valeur de `_groupe` réclamant les lignes de tous les groupes de la page
   * (voir core.listing.TOUS_LES_GROUPES). */
  var TOUS_LES_GROUPES = '*';

  /* Marque une requête qui ne vient que faire retenir la sélection
   * (voir core.memoire_listing.PARAM_MEMO). */
  var PARAM_MEMO = '_memo';

  /* Rang de la première ligne réclamée dans un groupe — ce que « Charger plus »
   * fait varier (voir core.listing.PARAM_DECALAGE). */
  var PARAM_DECALAGE = '_decalage';

  /* Au-delà de ce nombre de lignes, une vue n'est pas préchargée : ses groupes
   * iront les chercher au dépliage, un par un. C'est le garde-fou qui empêche
   * de retomber dans la page de plusieurs méga-octets — sur une sélection
   * énorme, tout précharger coûterait plus cher que ce qu'on y gagne. */
  var MAX_LIGNES_PRECHARGEES = 1500;

  function enfantsDirects(racine, chemin) {
    return racine.querySelectorAll('[data-parent="' + chemin + '"]');
  }

  function descendance(racine, chemin) {
    // Le préfixe suivi d'un tiret évite de confondre « 1 » avec « 11 ».
    return racine.querySelectorAll('[data-parent^="' + chemin + '-"]');
  }

  function urlDuGroupe(chemin, decalage) {
    var params = new URLSearchParams(location.search);
    params.set('_groupe', chemin);
    if (decalage) params.set(PARAM_DECALAGE, decalage);
    return location.pathname + '?' + params.toString();
  }

  /* Une réponse analysée au plus une fois par forme, même si vingt-cinq bandes
   * y puisent : analyser deux cents kilo-octets de HTML par groupe coûterait
   * plus cher que l'aller-retour lui-même. */
  function analyseur(html) {
    var doc = null, docTable = null;
    function lire(texte) {
      return new DOMParser().parseFromString(texte, 'text/html');
    }
    return {
      simple: function () { return doc || (doc = lire(html)); },
      enTableau: function () {
        return docTable ||
          (docTable = lire('<table><tbody>' + html + '</tbody></table>'));
      }
    };
  }

  /* Le conteneur, dans la réponse, qui correspond à celui de l'en-tête visé.
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
  function lignesDu(analyse, chemin, entete) {
    var selecteur = '[data-parent="' + chemin + '"]';
    var doc = analyse.simple();
    var conteneur = conteneurJumeau(doc, chemin, entete);
    if (conteneur) return conteneur.querySelectorAll(selecteur);

    // Pas de bande jumelle — une réponse qui ne rendrait que les lignes. Rien à
    // cloisonner dans ce cas : on prend ce qu'il y a, comme avant.
    var trouvees = doc.querySelectorAll(selecteur);
    if (trouvees.length) return trouvees;

    // Toujours rien : peut-être un fragment de `<tr>` nus, que l'analyseur
    // jette hors d'un tableau. On lui en donne un.
    doc = analyse.enTableau();
    conteneur = conteneurJumeau(doc, chemin, entete);
    return (conteneur || doc).querySelectorAll(selecteur);
  }

  /* Range les lignes sous leur bande. `visible` dit si le groupe est ouvert :
   * le préchargement, lui, les pose repliées. */
  function inserer(ancre, lignes, visible) {
    lignes.forEach(function (el) {
      // importNode : le nœud vient d'un autre document.
      var copie = document.importNode(el, true);
      copie.style.display = visible ? '' : 'none';
      ancre.insertAdjacentElement('afterend', copie);
      ancre = copie;
    });
  }

  function poser(entete, lignes, visible) {
    inserer(entete, lignes, visible);
    entete.dataset.charge = '1';
  }

  function demander(chemin, decalage) {
    return fetch(urlDuGroupe(chemin, decalage), {
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest' }
    }).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.text();
    });
  }

  /* Va chercher les lignes d'un seul groupe et les insère après son en-tête. */
  function charger(entete, chemin) {
    entete.classList.add('lst-chargement');
    return demander(chemin)
      .then(function (html) {
        // Le préchargement a pu arriver le premier pendant que la requête
        // volait : reposer les mêmes lignes les mettrait en double.
        if (entete.dataset.charge === '1') return;
        poser(entete, lignesDu(analyseur(html), chemin, entete), true);
      })
      .catch(function () {
        if (window.showToast) {
          showToast("Impossible d'ouvrir ce groupe.", 'error');
        }
      })
      .finally(function () { entete.classList.remove('lst-chargement'); });
  }

  /* ── Les gros groupes arrivent par lots ──
   *
   * Un groupe de trente mille lignes ne sort pas d'un bloc : le serveur n'en
   * rend qu'un lot (core.listing.TAILLE_LOT_GROUPE), clos par une entrée
   * « Charger plus » qui porte le rang du suivant. La redemander remplace cette
   * entrée par le lot d'après — et par la suivante, s'il en reste encore.
   *
   * L'entrée porte `data-parent` comme une ligne de données : replier le groupe
   * la cache avec elles, sans qu'il y ait rien de particulier à prévoir.
   */
  function chargerPlus(plus) {
    if (plus.classList.contains('lst-chargement')) return;   // déjà en vol
    var chemin = plus.dataset.parent;
    var racine = plus.parentElement;
    // L'en-tête du groupe sert de repère pour retrouver la bonne vue dans la
    // réponse — tableau ou kanban, voir `conteneurJumeau`.
    var entete = racine.querySelector('.lst-groupe[data-chemin="' + chemin + '"]');
    if (!entete) return;

    plus.classList.add('lst-chargement');
    demander(chemin, plus.dataset.suite)
      .then(function (html) {
        var lignes = lignesDu(analyseur(html), chemin, entete);
        if (!lignes.length) return;
        // Le lot suivant vient avec sa propre entrée « Charger plus », s'il en
        // reste : elle est dans `lignes`, puisqu'elle porte le même `data-parent`.
        inserer(plus, lignes, true);
        plus.remove();
      })
      .catch(function () {
        if (window.showToast) {
          showToast("Impossible de charger la suite de ce groupe.", 'error');
        }
      })
      .finally(function () { plus.classList.remove('lst-chargement'); });
  }

  /* Les bandes feuilles qui n'ont pas encore leurs lignes, par conteneur. */
  function vuesAPrecharger() {
    var parVue = new Map();
    document.querySelectorAll('.lst-groupe[data-feuille="1"]').forEach(function (b) {
      if (b.dataset.charge === '1' || b.classList.contains('lst-chargement')) return;
      var vue = b.parentElement;
      if (!parVue.has(vue)) parVue.set(vue, []);
      parVue.get(vue).push(b);
    });
    var retenues = [];
    parVue.forEach(function (bandes) {
      var total = bandes.reduce(function (n, b) {
        return n + (parseInt(b.dataset.total, 10) || 0);
      }, 0);
      if (total <= MAX_LIGNES_PRECHARGEES) retenues.push(bandes);
    });
    return retenues;
  }

  var prechargementEnVol = false;

  /* Va chercher d'un coup les lignes de tous les groupes de la page. */
  function precharger() {
    if (prechargementEnVol) return Promise.resolve();
    var vues = vuesAPrecharger();
    if (!vues.length) return Promise.resolve();
    prechargementEnVol = true;
    return demander(TOUS_LES_GROUPES)
      .then(function (html) {
        var analyse = analyseur(html);
        vues.forEach(function (bandes) {
          bandes.forEach(function (entete) {
            // Un groupe déplié à la main pendant le vol a déjà ses lignes, ou
            // les reçoit à l'instant : dans les deux cas on le laisse.
            if (entete.dataset.charge === '1' ||
                entete.classList.contains('lst-chargement')) return;
            poser(entete, lignesDu(analyse, entete.dataset.chemin, entete), false);
          });
        });
      })
      // Silence volontaire : personne n'a rien demandé. Un groupe non préchargé
      // ira chercher ses lignes au dépliage, et c'est là qu'on se plaindra.
      .catch(function () {})
      .finally(function () { prechargementEnVol = false; });
  }

  /* ── L'état déplié voyage avec les critères ──
   *
   * Déplier un groupe, ouvrir une fiche, revenir : l'arbre revenait fermé. Rien
   * ne notait l'état déplié — ni l'URL, ni la mémoire de sélection du serveur,
   * qui retient le filtre et le regroupement mais pas ce qu'on avait ouvert.
   *
   * Le rattraper après l'affichage ne suffit pas : la page arrive fermée puis
   * saute, et ce sursaut se voit. Les filtres n'ont jamais ce défaut parce
   * qu'ils arrivent déjà appliqués dans le HTML — le serveur redirige vers
   * l'URL portant la sélection retenue, et la page rendue est la bonne du
   * premier coup.
   *
   * Les chemins ouverts rejoignent donc les critères dans l'URL. La mémoire des
   * listes les retient comme les autres, et le serveur rend ces groupes déjà
   * dépliés, leurs lignes comprises : il n'y a plus rien à rouvrir, donc plus
   * rien qui saute.
   *
   * Le numéro de page fait partie de la valeur. Un chemin est positionnel — « 0 »
   * est le premier groupe *de la page affichée* — et les liens de pagination
   * recopient les paramètres courants : sans lui, passer à la page suivante
   * déplierait un groupe sans rapport.
   */
  function noterOuverts() {
    var ouverts = [];
    document.querySelectorAll('.lst-groupe.open').forEach(function (bande) {
      if (ouverts.indexOf(bande.dataset.chemin) === -1) {
        ouverts.push(bande.dataset.chemin);
      }
    });
    var params = new URLSearchParams(location.search);
    if (ouverts.length) {
      params.set('ouverts', (params.get('page') || '1') + ':' + ouverts.join(','));
    } else {
      params.delete('ouverts');
    }
    var chaine = params.toString();
    try {
      // `replaceState` et non `pushState` : déplier n'est pas une étape de
      // navigation. La flèche Retour doit ramener à l'écran précédent, pas
      // défaire un clic.
      history.replaceState(history.state, '',
                           location.pathname + (chaine ? '?' + chaine : ''));
    } catch (e) {
      /* Historique refusé : on perd l'état déplié, rien de plus. */
    }
    memoriser(params);
  }

  /* Dit au serveur ce qui est ouvert, pour qu'il le retienne.
   *
   * `replaceState` ne parle qu'au navigateur : l'adresse change, personne
   * d'autre ne l'apprend. Revenir par la flèche Précédent marchait donc — c'est
   * le navigateur qui redemande l'URL complète —, mais pas par le bouton
   * « Retour » d'une fiche, qui pointe vers la liste nue et s'en remet à la
   * mémoire de sélection (core.memoire_listing). Celle-ci ramenait le filtre et
   * le regroupement, qu'un rechargement lui avait appris, et jamais les groupes
   * ouverts, que rien ne lui avait dits.
   *
   * La requête ne rend rien (204), ne bloque rien, et `keepalive` la laisse
   * arriver même si on ouvre une fiche dans la foulée.
   */
  function memoriser(params) {
    var copie = new URLSearchParams(params);
    copie.set(PARAM_MEMO, '1');
    try {
      fetch(location.pathname + '?' + copie.toString(), {
        credentials: 'same-origin',
        keepalive: true,
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
      })
        // Silence volontaire : rien à l'écran n'en dépend. Au pire la mémoire
        // ignore ce dépliage, et le retour ramènera la liste repliée.
        .catch(function () {});
    } catch (e) {
      /* `fetch` indisponible : même conséquence, et rien à dire de plus. */
    }
  }

  function ouvrir(entete, chemin) {
    entete.classList.add('open');
    enfantsDirects(entete.parentElement, chemin)
      .forEach(function (el) { el.style.display = ''; });
    noterOuverts();
  }

  function basculer(ligne) {
    var chemin = ligne.dataset.chemin;
    var racine = ligne.parentElement;

    if (!ligne.classList.contains('open')) {
      // Un groupe feuille que le préchargement n'a pas atteint n'a pas ses
      // lignes : il va les chercher lui-même.
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
    noterOuverts();
  }

  /* Après l'affichage, jamais pendant : le préchargement ne doit rien retarder
   * de ce qu'on regarde. `requestIdleCallback` attend que le navigateur n'ait
   * plus rien d'urgent ; là où il n'existe pas, un délai court en tient lieu. */
  function prechargerQuandLibre() {
    var faire = function () { precharger(); };
    if (window.requestIdleCallback) {
      requestIdleCallback(faire, { timeout: 2000 });
    } else {
      setTimeout(faire, 300);
    }
  }

  window.lstBasculerGroupe = basculer;
  window.lstChargerPlus = chargerPlus;
  window.lstPrecharger = prechargerQuandLibre;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', prechargerQuandLibre);
  } else {
    prechargerQuandLibre();
  }
})();
