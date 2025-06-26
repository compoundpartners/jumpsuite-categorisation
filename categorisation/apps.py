from django.apps import AppConfig


class CategorisationConfig(AppConfig):
    name = "categorisation"
    default_auto_field = "django.db.models.AutoField"

    def ready(self):
        from categorisation.admin import setup_admin_integration
        setup_admin_integration()