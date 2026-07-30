/* Constructeur de filtre personnalisé (panneau latéral du menu Filtres).
 *
 * Chaque condition est un triplet champ / opérateur / valeur. Elles partent dans
 * l'URL sous forme de trois listes parallèles `cf`, `co`, `cv` (plus `cm` pour le
 * mode) : trois listes évitent d'inventer un séparateur, donc d'avoir à gérer son
 * échappement quand une valeur en contient un.
 *
 * L'application passe par refreshList : pas de rechargement de page, et l'état
 * survit au bouton Retour comme le reste des filtres.
 */
(function () {
  'use strict';

  // Renseignés depuis le bloc JSON de la page : les champs, les opérateurs par
  // catégorie de champ (donnés une fois pour toutes plutôt que répétés à chaque
  // champ, il y en a plusieurs centaines) et les opérateurs sans valeur.
  var CHAMPS = [];
  var OPERATEURS = {};
  var SANS_VALEUR = [];
  // Type de saisie selon la catégorie du champ. Les catégories `_json` visent
  // des valeurs rangées dans un JSONField : la saisie est la même, seuls les
  // opérateurs proposés diffèrent (cf. core.listing.OPERATEURS).
  var SAISIE = {date: 'date', date_json: 'date', nombre: 'number', nombre_json: 'number'};

  function lire(id) {
    var el = document.getElementById(id);
    if (!el) return null;
    try { return JSON.parse(el.textContent); } catch (e) { return null; }
  }

  function champParChemin(chemin) {
    return CHAMPS.find(function (c) { return c.chemin === chemin; });
  }

  function hote() { return document.getElementById('lstf-lignes'); }

  /* Construit la saisie adaptée au champ et à l'opérateur : liste déroulante
     pour un champ à valeurs connues, date, nombre ou texte sinon. Rien du tout
     pour « est vide » et consorts, qui n'attendent aucune valeur. */
  function saisieValeur(champ, operateur, valeur) {
    if (SANS_VALEUR.indexOf(operateur) !== -1) return null;
    if (champ.choix && champ.choix.length) {
      var select = document.createElement('select');
      select.className = 'lstf-valeur';
      champ.choix.forEach(function (paire) {
        var o = document.createElement('option');
        o.value = paire[0];
        o.textContent = paire[1];
        if (String(paire[0]) === String(valeur)) o.selected = true;
        select.appendChild(o);
      });
      return select;
    }
    var input = document.createElement('input');
    input.className = 'lstf-valeur';
    input.type = SAISIE[champ.type] || 'text';
    input.value = valeur || '';
    return input;
  }

  function majOperateurs(ligne, champ, operateurChoisi) {
    var selOp = ligne.querySelector('.lstf-operateur');
    selOp.innerHTML = '';
    (OPERATEURS[champ.type] || []).forEach(function (op) {
      var o = document.createElement('option');
      o.value = op.code;
      o.textContent = op.libelle;
      if (op.code === operateurChoisi) o.selected = true;
      selOp.appendChild(o);
    });
  }

  /* La saisie vit dans un emplacement dédié : la remplacer ne dépend alors ni de
     son type ni de sa présence (les opérateurs « est vide » n'en ont aucune). */
  function majValeur(ligne, valeur) {
    var emplacement = ligne.querySelector('.lstf-valeur-slot');
    var champ = champParChemin(ligne.querySelector('.lstf-champ').value);
    var operateur = ligne.querySelector('.lstf-operateur').value;
    emplacement.innerHTML = '';
    var saisie = saisieValeur(champ, operateur, valeur);
    if (saisie) emplacement.appendChild(saisie);
  }

  function creerLigne(condition) {
    var ligne = document.createElement('div');
    ligne.className = 'lstf-ligne';

    var tete = document.createElement('div');
    tete.className = 'lstf-tete-ligne';

    var selChamp = document.createElement('select');
    selChamp.className = 'lstf-champ';
    // Champs rangés par groupe (le formulaire, ses onglets) : la liste se
    // parcourt comme le formulaire, sans quoi trois cents intitulés à plat
    // seraient impossibles à situer. Les champs arrivent déjà triés par groupe.
    var groupeCourant = null;
    var hote = selChamp;
    CHAMPS.forEach(function (c) {
      if (c.groupe !== groupeCourant) {
        groupeCourant = c.groupe;
        if (c.groupe) {
          hote = document.createElement('optgroup');
          hote.label = c.groupe;
          selChamp.appendChild(hote);
        } else {
          hote = selChamp;
        }
      }
      var o = document.createElement('option');
      o.value = c.chemin;
      o.textContent = c.libelle;
      if (condition && c.chemin === condition.champ) o.selected = true;
      hote.appendChild(o);
    });

    var retirer = document.createElement('button');
    retirer.type = 'button';
    retirer.className = 'lstf-retirer';
    retirer.textContent = '−';
    retirer.title = 'Retirer cette condition';
    retirer.onclick = function () { ligne.remove(); majEtat(); };

    tete.appendChild(selChamp);
    tete.appendChild(retirer);

    var selOp = document.createElement('select');
    selOp.className = 'lstf-operateur';

    var emplacement = document.createElement('div');
    emplacement.className = 'lstf-valeur-slot';

    ligne.appendChild(tete);
    ligne.appendChild(selOp);
    ligne.appendChild(emplacement);

    majOperateurs(ligne, champParChemin(selChamp.value), condition && condition.operateur);
    majValeur(ligne, condition && condition.valeur);

    // Changer de champ change les opérateurs possibles, donc la saisie.
    selChamp.onchange = function () {
      majOperateurs(ligne, champParChemin(selChamp.value), null);
      majValeur(ligne, '');
    };
    selOp.onchange = function () { majValeur(ligne, ''); };
    return ligne;
  }

  /* Le choix « toutes / au moins une » n'a de sens qu'à partir de deux
     conditions ; le message de panneau vide indique, lui, qu'appliquer en l'état
     retire le filtre personnalisé. */
  function majEtat() {
    var lignes = hote();
    if (!lignes) return;
    var n = lignes.querySelectorAll('.lstf-ligne').length;
    var mode = document.getElementById('lstf-mode');
    if (mode) mode.classList.toggle('lstf-visible', n > 1);

    var vide = lignes.parentNode.querySelector('.lstf-vide');
    if (n === 0 && !vide) {
      vide = document.createElement('div');
      vide.className = 'lstf-vide';
      vide.textContent = 'Aucune condition : appliquer retire le filtre personnalisé.';
      lignes.parentNode.insertBefore(vide, lignes.nextSibling);
    } else if (n > 0 && vide) {
      vide.remove();
    }
    placer();
  }

  window.lstfAjouterLigne = function () {
    var lignes = hote();
    if (!lignes) return;
    lignes.appendChild(creerLigne(null));
    majEtat();
  };

  /* Conditions en cours, lues dans l'URL. C'est la seule source fiable : un bloc
     rendu par le serveur ne suivrait pas les rafraîchissements AJAX. */
  function conditionsDeLUrl() {
    var params = new URLSearchParams(window.location.search);
    var champs = params.getAll('cf');
    var operateurs = params.getAll('co');
    var valeurs = params.getAll('cv');
    return champs.map(function (chemin, i) {
      return {champ: chemin, operateur: operateurs[i] || '', valeur: valeurs[i] || ''};
    }).filter(function (c) { return champParChemin(c.champ); });
  }

  /* Remonte le panneau quand il déborderait du bas de la fenêtre : il s'ouvre
     depuis la dernière entrée du menu, donc déjà bas dans l'écran. */
  function placer() {
    var entree = document.getElementById('lstf-entree');
    if (!entree) return;
    var panneau = entree.querySelector('.lstf-panneau');
    if (!panneau) return;
    panneau.style.top = '0px';
    // Hauteur nulle : le panneau est encore replié, il n'y a rien à placer. C'est
    // ce test — et non plus la présence d'une classe d'épinglage — qui distingue
    // les deux cas depuis que l'ouverture se fait au survol.
    var hauteur = panneau.offsetHeight;
    if (!hauteur) return;
    var haut = entree.getBoundingClientRect().top;
    var debord = haut + hauteur - (window.innerHeight - 8);
    if (debord > 0) panneau.style.top = '-' + Math.min(debord, Math.max(0, haut - 8)) + 'px';
  }

  /* Rebranché après chaque échange AJAX : la barre de contrôles est remplacée,
     donc le panneau aussi. Les conditions sont reconstruites depuis l'URL. */
  window.lstfInit = function () {
    var lignes = hote();
    if (!lignes) return;
    lignes.innerHTML = '';
    var existantes = conditionsDeLUrl();
    if (existantes.length) existantes.forEach(function (c) { lignes.appendChild(creerLigne(c)); });
    else lignes.appendChild(creerLigne(null));

    var params = new URLSearchParams(window.location.search);
    var mode = document.getElementById('lstf-mode-select');
    if (mode) mode.value = params.get('cm') === 'ou' ? 'ou' : 'et';
    majEtat();

    /* Le panneau sort et rentre au survol, par la seule règle CSS des sous-menus
       (cf. filtre_perso.html) : rien à épingler ici. Ne reste que son placement,
       le panneau étant plus haut que les autres sous-menus — sans quoi il
       déborderait sous le bas de la fenêtre.
       Affectation par propriété et non addEventListener : lstfInit est rappelé
       après chaque échange AJAX, on ne veut pas empiler les écouteurs. */
    var entree = document.getElementById('lstf-entree');
    if (entree) entree.onmouseenter = placer;
  };

  window.lstfBasculer = function (entree) {
    var ouvert = !entree.classList.contains('lstf-ouvert');
    entree.classList.toggle('lstf-ouvert', ouvert);
    if (ouvert) placer();
  };

  window.lstfAppliquer = function () {
    var params = new URLSearchParams(window.location.search);
    params.delete('cf'); params.delete('co'); params.delete('cv'); params.delete('cm');
    params.delete('page');

    var retenues = 0;
    document.querySelectorAll('#lstf-lignes .lstf-ligne').forEach(function (ligne) {
      var chemin = ligne.querySelector('.lstf-champ').value;
      var operateur = ligne.querySelector('.lstf-operateur').value;
      var champValeur = ligne.querySelector('.lstf-valeur');
      var valeur = champValeur ? champValeur.value : '';
      // Une condition attendant une valeur mais laissée vide est ignorée.
      if (SANS_VALEUR.indexOf(operateur) === -1 && !valeur) return;
      params.append('cf', chemin);
      params.append('co', operateur);
      params.append('cv', valeur);
      retenues++;
    });
    if (retenues > 1) params.set('cm', document.getElementById('lstf-mode-select').value);

    var url = window.location.pathname + (params.toString() ? '?' + params.toString() : '');
    if (window.refreshList) window.refreshList(url, true);
    else window.location = url;
  };

  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    var entree = document.getElementById('lstf-entree');
    if (!entree) return;
    entree.classList.remove('lstf-ouvert');
    // Le focus rendu, sans quoi le `:focus-within` de la brique continuerait
    // d'afficher le panneau que l'on vient de demander à fermer.
    if (entree.contains(document.activeElement)) document.activeElement.blur();
  });

  /* Survoler une autre entrée du menu replie le panneau épinglé.
   *
   * Sans cela il restait ouvert par-dessus le sous-menu de l'entrée survolée —
   * et comme il est la dernière entrée du menu, son panneau se peint au-dessus
   * de celui de toutes les entrées précédentes, qui semblait alors sortir
   * derrière lui. L'épinglage ne sert qu'à survivre aux fenêtres du système
   * ouvertes par ses propres listes déroulantes, pas à masquer le reste du menu.
   *
   * Écouteur au niveau du document, posé une seule fois : les entrées du menu
   * sont remplacées à chaque rafraîchissement AJAX.
   *
   * Vaut aussi pour le panneau des champs de « Ajouter un groupement
   * personnalisé », épinglé au clic pour le tactile.
   */
  document.addEventListener('mouseover', function (e) {
    if (!e.target.closest) return;
    var ligne = e.target.closest('.o-dd-item');
    if (!ligne) return;                       // hors d'un menu : on n'y touche pas
    document.querySelectorAll('.lstf-ouvert, .lstg-ouvert').forEach(function (epingle) {
      // Toujours à l'intérieur du panneau épinglé : rien à replier.
      if (epingle.contains(e.target)) return;
      // Un champ du panneau a le focus (liste déroulante déployée, date en cours
      // de saisie) : le replier perdrait la saisie.
      if (epingle.contains(document.activeElement)) return;
      epingle.classList.remove('lstf-ouvert');
      epingle.classList.remove('lstg-ouvert');
    });
  });

  var DONNEES = lire('lstf-champs') || {};
  CHAMPS = DONNEES.champs || [];
  OPERATEURS = DONNEES.operateurs || {};
  SANS_VALEUR = DONNEES.sans_valeur || [];
  if (document.readyState !== 'loading') lstfInit();
  else document.addEventListener('DOMContentLoaded', lstfInit);
})();
