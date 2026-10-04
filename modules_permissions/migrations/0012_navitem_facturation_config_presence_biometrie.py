from django.db import migrations

# Deux menus se testaient contre `hidden_navitem_codes` sans qu'aucune ligne
# NavItem leur corresponde. Le gabarit cherchait donc un code que la base ne
# contenait pas : le menu s'affichait toujours, et surtout il n'apparaissait
# nulle part dans la checklist de l'admin — impossible de le retirer à un
# groupe, puisqu'il n'y avait rien à décocher.
#
# C'est le genre d'écart qui ne se voit pas : le menu marche, le masquage ne
# marche pas, et rien ne le signale. Les deux codes sont repris tels quels des
# gabarits, et les libellés tels qu'ils s'affichent à l'écran — une case qui ne
# porte pas le nom du menu qu'elle gouverne ne se coche pas de bon cœur.
NOUVEAUX = [
    ('facturation.config', 'Configuration',      'facturation'),
    ('presence.biometrie', 'Réglages empreinte', 'presence'),
]

# `caisse.list` existe en base mais plus aucun gabarit ne le consulte : la case
# est là, on la coche, rien ne se passe. On la retire plutôt que de la laisser
# promettre un masquage qui n'a plus lieu. Les restrictions de groupe qui la
# visaient tombent avec elle — elles n'avaient déjà aucun effet.
RETIRE = 'caisse.list'


def poser(apps, schema_editor):
    NavItem = apps.get_model('modules_permissions', 'NavItem')
    Module = apps.get_model('modules_permissions', 'Module')
    for code, label, module_code in NOUVEAUX:
        module = Module.objects.filter(code=module_code).first()
        NavItem.objects.update_or_create(
            code=code, defaults={'label': label, 'module': module})
    NavItem.objects.filter(code=RETIRE).delete()


def retirer(apps, schema_editor):
    NavItem = apps.get_model('modules_permissions', 'NavItem')
    Module = apps.get_model('modules_permissions', 'Module')
    NavItem.objects.filter(code__in=[c for c, _, _ in NOUVEAUX]).delete()
    module = Module.objects.filter(code='caisse').first()
    NavItem.objects.update_or_create(
        code=RETIRE, defaults={'label': 'Caisses', 'module': module})


class Migration(migrations.Migration):

    dependencies = [
        ('modules_permissions', '0011_navitem_rapports_link_hors_module'),
    ]

    operations = [
        migrations.RunPython(poser, retirer),
    ]
