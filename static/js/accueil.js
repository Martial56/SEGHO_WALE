/* Page d'accueil — lanceur de modules.
   Gabarit : templates/core/dashboard.html ; tuiles : core/modules_accueil.py.

   1. Recherche en direct : une tuile reste visible si elle contient tous les
      mots tapés. Entrée ouvre le premier résultat, Ctrl+K place le curseur
      dans la recherche, Échap la vide.
   2. Vue « Icônes » ou « Liste », retenue par le navigateur.
   3. Rafraîchissement des compteurs (sous-titres et pastilles) toutes les
      30 secondes, à partir de core.views.dashboard_stats_json.
*/
(function () {
  'use strict';

  /* ══ 1. RECHERCHE ═══════════════════════════════════════════════════════ */

  var champ = document.getElementById('accueil-recherche');
  var vide = document.getElementById('accueil-vide');
  var tuiles = Array.prototype.slice.call(document.querySelectorAll('.accueil-grille .tuile'));
  var grille = document.getElementById('accueil-grille');

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
      t.hidden = !mots.every(function (m) { return t._recherche.indexOf(m) !== -1; });
    });

    if (!vide) return;
    if (tuilesVisibles().length) {
      vide.hidden = true;
      vide.textContent = '';
    } else {
      vide.hidden = false;
      vide.textContent = 'Aucun module ne correspond à « ' + saisie.trim() + ' ».';
    }
  }

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

  /* ══ 2. VUE : « Icônes » ou « Liste » (lignes compactes) ═══════════════
     Purement CSS (attribut data-vue de la grille) ; le choix est retenu par
     le navigateur, et la page s'affiche normalement s'il n'est pas lisible. */

  var VUES = ['icones', 'liste'];
  var CLE_VUE = 'accueil-vue';
  var boutonsVue = Array.prototype.slice.call(document.querySelectorAll('.accueil-mode[data-vue]'));

  function appliquerVue(vue) {
    if (!grille || VUES.indexOf(vue) === -1) return;
    grille.setAttribute('data-vue', vue);
    boutonsVue.forEach(function (b) {
      b.setAttribute('aria-pressed', b.getAttribute('data-vue') === vue ? 'true' : 'false');
    });
  }

  boutonsVue.forEach(function (b) {
    b.addEventListener('click', function () {
      var vue = b.getAttribute('data-vue');
      appliquerVue(vue);
      try { localStorage.setItem(CLE_VUE, vue); } catch (e) {}
    });
  });

  var vueMemorisee = null;
  try { vueMemorisee = localStorage.getItem(CLE_VUE); } catch (e) {}
  if (vueMemorisee) appliquerVue(vueMemorisee);

  // Retour arrière : le navigateur peut avoir gardé la saisie précédente.
  appliquer();
  window.addEventListener('pageshow', function (e) {
    if (e.persisted) appliquer();
  });

  /* ══ 3. RAFRAÎCHISSEMENT DES COMPTEURS ══════════════════════════════════ */

  var INTERVALLE = 30000; // 30 secondes
  var URL_STATS = window.ACCUEIL_STATS_URL;
  var minuteur = null;

  // Compteurs repris tels quels dans les sous-titres (attribut data-stat).
  var STATS_SIMPLES = ['patients_total', 'rdv_today', 'hospitalisations',
                       'soins_aujourd_hui', 'analyses_pending', 'employes_actifs'];

  // Petit pulse visuel (CSS .stat-flash) pour signaler qu'un nombre vient de
  // changer sous nos yeux. Sans effet si l'utilisateur refuse les animations
  // (le mot-clé n'existe alors pas dans la feuille de style).
  function declencherFlash(el) {
    el.classList.remove('stat-flash');
    void el.offsetWidth; // force le navigateur à « oublier » l'animation précédente
    el.classList.add('stat-flash');
  }

  function majStat(cle, valeur) {
    if (valeur === undefined) return;
    document.querySelectorAll('[data-stat="' + cle + '"]').forEach(function (el) {
      if (el.textContent != valeur) {
        el.textContent = valeur;
        declencherFlash(el);
      }
    });
  }

  // Sous-titre réécrit en entier selon que le compteur est nul ou non.
  // Le nombre est posé par textContent : jamais de HTML venu du réseau.
  function majSousTitre(nom, valeur, cleStat, suite, texteSiZero) {
    var el = document.querySelector('[data-sous-titre="' + nom + '"]');
    if (!el || valeur === undefined) return;
    var precedente = el.getAttribute('data-valeur-precedente');
    el.setAttribute('data-valeur-precedente', valeur);
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
    if (precedente !== null && Number(precedente) !== valeur) declencherFlash(el);
  }

  function majPastille(cle, total) {
    var p = document.querySelector('[data-pastille="' + cle + '"]');
    if (!p) return;
    var n = Number(total) || 0;
    var nombre = p.querySelector('[data-pastille-nombre]');
    var precedent = nombre ? Number(nombre.textContent) || 0 : 0;
    if (nombre) nombre.textContent = n;
    var etaitCachee = p.hidden;
    p.hidden = n <= 0;
    if (n > 0 && (n !== precedent || etaitCachee)) declencherFlash(p);
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
