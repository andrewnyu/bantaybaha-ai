from pathlib import Path

from django.core.management import call_command
from django.db.models.signals import post_migrate
from django.db.utils import OperationalError, ProgrammingError


def load_evacuation_centers(sender, **kwargs) -> None:
    from .models import EvacuationCenter

    try:
        if EvacuationCenter.objects.exists():
            return
    except (OperationalError, ProgrammingError):
        return

    fixture_path = Path(__file__).resolve().parent / "fixtures" / "evacuation_centers.json"
    call_command("loaddata", str(fixture_path), verbosity=0)


def register_signals(app_config) -> None:
    post_migrate.connect(
        load_evacuation_centers,
        sender=app_config,
        dispatch_uid="core.load_evacuation_centers",
    )
