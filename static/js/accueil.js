/* Page d'accueil — lanceur de modules.
   Gabarit : templates/core/dashboard.html ; tuiles : core/modules_accueil.py.

   1. Rafraîchissement des compteurs (sous-titres et pastilles) toutes les
      30 secondes, à partir de core.views.dashboard_stats_json.
   2. Filtres par domaine et recherche en direct : une tuile reste visible si
      elle appartient au domaine choisi ET contient tous les mots tapés.
      Entrée ouvre le premier résultat, Ctrl+K place le curseur dans la
      recherche, Échap la vide.
*/
(function () {
  'use strict';

  /* ══ 2. FILTRES ET RECHERCHE ════════════════════════════════════════════ */

  var champ = document.getElementById('accueil-recherche');
  var vide = document.getElementById('accueil-vide');
  var tuiles = Array.prototype.slice.call(document.querySelectorAll('.accueil-grille .tuile'));
  var filtres = Array.prototype.slice.call(document.querySelectorAll('.accueil-filtre'));
  var domaineActif = 'tous';

  // « Évaluation », « evaluation » et « EVALUATION » se valent.
  function normaliser(texte) {
    return (texte || '').normalize('NFD').replace(/[̀-ͯ]/g, '')
                        .toLowerCase().trim();
  }

  // Texte de recherche de chaque tuile (libellé + mots-clés), normalisé une
  // fois pour toutes.
  tuiles.forEach(function (t) {
    t._recherche = normaliser(t.getAttribute('data-recherche'));
  });

  function tuilesVisibles() {
    return tuiles.filter(function (t) { return !t.hidden; });
  }

  function appliquer() {
    var saisie = champ ? champ.value : '';
    var mots = normaliser(saisie).split(/\s+/).filter(Boolean);

    tuiles.forEach(function (t) {
      var bonDomaine = domaineActif === 'tous' || t.getAttribute('data-domaine') === domaineActif;
      var trouve = mots.every(function (m) { return t._recherche.indexOf(m) !== -1; });
      t.hidden = !(bonDomaine && trouve);
    });

    if (!vide) return;
    if (tuilesVisibles().length) {
      vide.hidden = true;
      vide.textContent = '';
    } else {
      vide.hidden = false;
      vide.textContent = saisie.trim()
        ? 'Aucun module ne correspond à « ' + saisie.trim() + ' »'
          + (domaineActif !== 'tous' ? ' dans ce domaine.' : '.')
        : 'Aucun module dans ce domaine.';
    }
  }

  filtres.forEach(function (bouton) {
    bouton.addEventListener('click', function () {
      domaineActif = bouton.getAttribute('data-filtre');
      filtres.forEach(function (b) {
        b.setAttribute('aria-pressed', b === bouton ? 'true' : 'false');
      });
      appliquer();
    });
  });

  if (champ) {
    champ.addEventListener('input', appliquer);
    champ.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') {
        var premiere = tuilesVisibles()[0];
        if (premiere) {
          e.preventDefault();
          // Un vrai clic, pour que les écouteurs de base.html (chargement de
          // page) réagissent comme à un clic de souris.
          premiere.click();
        }
      } else if (e.key === 'Escape' && champ.value) {
        e.preventDefault();
        champ.value = '';
        appliquer();
      }
    });
  }

  // Ctrl+K (Cmd+K sur Mac) : vers la recherche, d'où que l'on soit.
  document.addEventListener('keydown', function (e) {
    if (!champ) return;
    if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && (e.key === 'k' || e.key === 'K')) {
      e.preventDefault();
      champ.focus();
      champ.select();
    }
  });

  // Retour arrière : le navigateur peut avoir gardé la saisie précédente.
  appliquer();
  window.addEventListener('pageshow', function (e) {
    if (e.persisted) appliquer();
  });

  /* ══ 1. RAFRAÎCHISSEMENT DES COMPTEURS ══════════════════════════════════ */

  var INTERVALLE = 30000; // 30 secondes
  var URL_STATS = window.ACCUEIL_STATS_URL;
  var minuteur = null;

  // Compteurs repris tels quels dans les sous-titres (attribut data-stat).
  var STATS_SIMPLES = ['patients_total', 'rdv_today', 'hospitalisations',
                       'soins_aujourd_hui', 'analyses_pending', 'employes_actifs'];

  function majStat(cle, valeur) {
    if (valeur === undefined) return;
    document.querySelectorAll('[data-stat="' + cle + '"]').forEach(function (el) {
      if (el.textContent != valeur) el.textContent = valeur;
    });
  }

  // Sous-titre réécrit en entier selon que le compteur est nul ou non.
  // Le nombre est posé par textContent : jamais de HTML venu du réseau.
  function majSousTitre(nom, valeur, cleStat, suite, texteSiZero) {
    var el = document.querySelector('[data-sous-titre="' + nom + '"]');
    if (!el || valeur === undefined) return;
    el.textContent = '';
    if (valeur > 0) {
      var nombre = document.createElement('span');
      nombre.setAttribute('data-stat', cleStat);
      nombre.textContent = valeur;
      el.appendChild(nombre);
      el.appendChild(document.createTextNode(suite));
    } else {
      el.textContent = texteSiZero;
    }
  }

  function majPastille(cle, total) {
    var p = document.querySelector('[data-pastille="' + cle + '"]');
    if (!p) return;
    var n = Number(total) || 0;
    var nombre = p.querySelector('[data-pastille-nombre]');
    if (nombre) nombre.textContent = n;
    p.hidden = n <= 0;
  }

  function rafraichir() {
    if (!URL_STATS) return;
    fetch(URL_STATS, { credentials: 'same-origin', cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (donnees) {
        if (!donnees) return;

        STATS_SIMPLES.forEach(function (cle) { majStat(cle, donnees[cle]); });

        majSousTitre('pharmacie', donnees.medicaments_alerte,
                     'medicaments_alerte', ' alertes', 'Stock OK');
        majSousTitre('factures', donnees.factures_impayees,
                     'factures_impayees', ' impayée(s)', 'À jour');

        // Le serveur ne renvoie que les modules où il reste du travail : une
        // pastille absente de la réponse doit donc s'éteindre.
        var recues = donnees.pastilles || {};
        ['hospitalisation', 'consultations', 'caisse'].forEach(function (cle) {
          majPastille(cle, recues[cle]);
        });
        majPastille('pharmacie', donnees.medicaments_alerte);
      })
      .catch(function () {});
  }

  function demarrer() {
    clearInterval(minuteur);
    minuteur = setInterval(rafraichir, INTERVALLE);
  }

  // Au chargement…
  rafraichir();
  demarrer();

  // …au retour sur l'onglet (en pause tant qu'il est caché)…
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') {
      rafraichir();
      demarrer();
    } else {
      clearInterval(minuteur);
    }
  });

  // …et au retour arrière, quand le navigateur ressert la page de son cache.
  window.addEventListener('pageshow', function (e) {
    if (e.persisted) rafraichir();
  });
})();
