"""
Commande d'import pour Articleservice depuis un fichier JSON.

Usage :
    python manage.py import_articles chemin/vers/fichier.json
    python manage.py import_articles chemin/vers/fichier.json --update
    python manage.py import_articles chemin/vers/fichier.json --dry-run

La clé d'unicité est `reference_interne`.
Les FK nulles dans le JSON (categorie_id, unite_mesure_id, etc.) sont ignorées.
"""

import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from services.models import (
    Articleservice, CategorieArticle,
    FamilleArticle, CompagniePharma,
)
from stock.models import UniteMesure
from django.contrib.auth.models import User

# Valeurs du JSON source → choix valides du modèle
TYPE_ARTICLE_MAP = {
    'service':      'prestation',
    'prestation':   'prestation',
    'consommable':  'consommable',
    'stockable':    'stockable',
    'autre':        'autre',
}


def _fk_or_none(model_class, json_id):
    """Résout un FK par ID JSON ; retourne None si l'ID est null ou introuvable."""
    if not json_id:
        return None
    try:
        return model_class.objects.get(pk=json_id)
    except model_class.DoesNotExist:
        return None


def _bool(val):
    return bool(val)


class Command(BaseCommand):
    help = "Importe des articles/services depuis un fichier JSON"

    def add_arguments(self, parser):
        parser.add_argument('fichier', type=str, help='Chemin vers le fichier JSON')
        parser.add_argument(
            '--update', action='store_true',
            help='Mettre à jour les articles existants (sinon skip)',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Simuler sans rien écrire en base',
        )

    def handle(self, *args, **options):
        chemin = Path(options['fichier'])
        if not chemin.exists():
            raise CommandError(f'Fichier introuvable : {chemin}')

        with open(chemin, encoding='utf-8') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                raise CommandError(f'JSON invalide : {e}')

        dry_run  = options['dry_run']
        do_update = options['update']
        created = updated = skipped = errors = 0

        self.stdout.write(f'→ Import de {len(data)} article(s){"  [DRY-RUN]" if dry_run else ""}…')

        for item in data:
            ref = item.get('reference_interne', '').strip()
            nom = item.get('nom', '').strip()

            if not ref and not nom:
                self.stdout.write(self.style.WARNING(f'  Ligne ignorée (pas de référence ni de nom) : id={item.get("id")}'))
                errors += 1
                continue

            # ── Résolution des FK ────────────────────────────────────────────
            categorie          = _fk_or_none(CategorieArticle, item.get('categorie_id'))
            unite_mesure       = _fk_or_none(UniteMesure,      item.get('unite_mesure_id'))
            unite_achat        = _fk_or_none(UniteMesure,      item.get('unite_achat_id'))
            famille            = _fk_or_none(FamilleArticle,   item.get('famille_id'))
            compagnie          = _fk_or_none(CompagniePharma,  item.get('compagnie_pharmaceutique_id'))
            responsable        = _fk_or_none(User,             item.get('responsable_id'))
            cree_par           = _fk_or_none(User,             item.get('cree_par_id'))

            # ── Mapping type_article ─────────────────────────────────────────
            type_article_raw = item.get('type_article', 'prestation')
            type_article = TYPE_ARTICLE_MAP.get(type_article_raw, 'prestation')

            defaults = {
                'nom':                           nom,
                'actif':                         _bool(item.get('actif', True)),
                'favori':                        _bool(item.get('favori', False)),
                'peut_etre_vendu':               _bool(item.get('peut_etre_vendu', True)),
                'peut_etre_achete':              _bool(item.get('peut_etre_achete', False)),
                # Médicament
                'forme':                         item.get('forme', ''),
                'voie_administration':           item.get('voie_administration', ''),
                'dosage':                        item.get('dosage', ''),
                'dosage_unite':                  item.get('dosage_unite', ''),
                'quantite_prescription_manuelle':_bool(item.get('quantite_prescription_manuelle', False)),
                'frequence':                     item.get('frequence', ''),
                'composant_actif':               item.get('composant_actif', ''),
                'effet_therapeutique':           item.get('effet_therapeutique', ''),
                'effets_indesirables':           item.get('effets_indesirables', ''),
                'compagnie_pharmaceutique':      compagnie,
                'code_produit':                  item.get('code_produit', ''),
                'url_produit':                   item.get('url_produit', ''),
                'nom_produit_fabricant':         item.get('nom_produit_fabricant', ''),
                'avertissement_grossesse':       _bool(item.get('avertissement_grossesse', False)),
                'avertissement_lactation':       _bool(item.get('avertissement_lactation', False)),
                'indications':                   item.get('indications', ''),
                'remarques':                     item.get('remarques', ''),
                # Général
                'type_article':                  type_article,
                'type_produit_hospitalier':      item.get('type_produit_hospitalier', ''),
                'politique_facturation':         item.get('politique_facturation', 'qtes_commandees'),
                'refacturer_depenses':           item.get('refacturer_depenses', 'non'),
                'unite_mesure':                  unite_mesure,
                'unite_achat':                   unite_achat,
                'prix_vente':                    item.get('prix_vente', 0),
                'taxes_vente':                   item.get('taxes_vente', ''),
                'cout':                          item.get('cout', 0),
                'categorie':                     categorie,
                'code_barres':                   item.get('code_barres', ''),
                'famille':                       famille,
                'notes_internes':                item.get('notes_internes', ''),
                # Stock
                'quantite_stock':                item.get('quantite_stock', 0),
                'quantite_alerte':               item.get('quantite_alerte', 0),
                # Vente / Achat
                'description_vente':             item.get('description_vente', ''),
                'taxes_fournisseur':             item.get('taxes_fournisseur', ''),
                'politique_controle':            item.get('politique_controle', 'qtes_recues'),
                'description_achat':             item.get('description_achat', ''),
                # Stock logistique
                'responsable':                   responsable,
                'poids':                         item.get('poids', 0),
                'volume':                        item.get('volume', 0),
                'delai_livraison_client':        item.get('delai_livraison_client', 0),
                'description_reception':         item.get('description_reception', ''),
                'description_livraison':         item.get('description_livraison', ''),
                'description_transfert':         item.get('description_transfert', ''),
                # Comptabilité
                'compte_revenus':                item.get('compte_revenus', ''),
                'compte_charges':                item.get('compte_charges', ''),
                'compte_ecart_prix':             item.get('compte_ecart_prix', ''),
                # Meta
                'cree_par':                      cree_par,
            }

            if dry_run:
                action = 'CRÉER' if not Articleservice.objects.filter(reference_interne=ref).exists() else ('MAJ' if do_update else 'SKIP')
                self.stdout.write(f'  [{action}] {ref} — {nom}')
                if action == 'CRÉER':
                    created += 1
                elif action == 'MAJ':
                    updated += 1
                else:
                    skipped += 1
                continue

            # ── Clé de recherche : reference_interne si présente, sinon nom ──
            if ref:
                obj, was_created = Articleservice.objects.get_or_create(
                    reference_interne=ref, defaults=defaults
                )
            else:
                obj, was_created = Articleservice.objects.get_or_create(
                    nom=nom, defaults=defaults
                )

            if was_created:
                created += 1
            elif do_update:
                for champ, valeur in defaults.items():
                    setattr(obj, champ, valeur)
                obj.save()
                updated += 1
            else:
                skipped += 1

        self.stdout.write(self.style.SUCCESS(
            f'  {created} créé(s), {updated} mis à jour, {skipped} ignoré(s), {errors} erreur(s)'
        ))
        if dry_run:
            self.stdout.write(self.style.WARNING('  ↑ DRY-RUN : rien n\'a été écrit en base.'))
        else:
            self.stdout.write(self.style.SUCCESS('✓ Import articles terminé.'))
