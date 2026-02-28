from django.db.models.signals import post_migrate
from django.db.utils import OperationalError, ProgrammingError


def load_evacuation_centers(sender, **kwargs) -> None:
    from .models import EvacuationCenter

    try:
        # Refresh to this project's known Negros Island fixture list after each migrate.
        desired = {
            "Bacolod City Hall Gym": (10.6769, 122.9518, 2500),
            "Bacolod Sports Complex": (10.6360, 122.9382, 1800),
            "Silay City Hall": (10.7938, 122.9721, 1200),
            "Talisay City Gymnasium": (10.7315, 122.9714, 900),
            "Kabankalan City Multipurpose Hall": (9.9850, 122.8108, 2000),
            "Dumaguete City Sports Arena": (9.3075, 123.3050, 1500),
            "Bayawan City Hall Gym": (9.3753, 122.8082, 1100),
            "Bais City Hall Gym": (9.5895, 123.1163, 1000),
            "Valencia City Sports Center": (9.2767, 122.9019, 1300),
        }

        desired_names = set(desired)
        EvacuationCenter.objects.exclude(name__in=desired_names).delete()
        for name, (lat, lng, capacity) in desired.items():
            EvacuationCenter.objects.update_or_create(
                name=name,
                defaults={
                    "latitude": lat,
                    "longitude": lng,
                    "capacity": capacity,
                },
            )

    except (OperationalError, ProgrammingError):
        return


def register_signals(app_config) -> None:
    post_migrate.connect(
        load_evacuation_centers,
        sender=app_config,
        dispatch_uid="core.load_evacuation_centers",
    )
