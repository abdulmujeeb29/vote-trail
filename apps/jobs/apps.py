from django.apps import AppConfig


class JobsConfig(AppConfig):
    name = "apps.jobs"
    label = "jobs"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from . import handlers  # noqa: F401  (registers every job handler)
