from django.apps import AppConfig


class BlockchainBridgeConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'blockchain_bridge'
    verbose_name = 'Blockchain'

    def ready(self):
        import blockchain_bridge.signals  # noqa: F401
