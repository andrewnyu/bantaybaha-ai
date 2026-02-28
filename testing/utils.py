from __future__ import annotations

from django.conf import settings


def is_testing_tab_enabled() -> bool:
    return bool(settings.DEBUG) or bool(settings.ENABLE_TESTING_TAB)
