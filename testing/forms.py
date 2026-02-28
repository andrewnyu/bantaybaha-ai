from __future__ import annotations

from datetime import datetime

from django import forms
from django.utils import timezone


KNOWN_STORM_START = datetime(2024, 11, 12, 6, 0)
KNOWN_STORM_END = datetime(2024, 11, 12, 18, 0)
KNOWN_NEGROS_OPTIONS = [("negros-island", "Negros Island")]

DATETIME_INPUT_FORMATS = [
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%dT%H:%M:%S",
]


class TestingBacktestForm(forms.Form):
    location_slug = forms.ChoiceField(choices=KNOWN_NEGROS_OPTIONS, initial="negros-island")
    start_datetime = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={"type": "datetime-local", "required": True}),
        input_formats=DATETIME_INPUT_FORMATS,
        help_text="Must be in the past (for demo/testing).",
    )
    end_datetime = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={"type": "datetime-local", "required": True}),
        input_formats=DATETIME_INPUT_FORMATS,
        help_text="Must be in the past and after start time.",
    )
    source_weather = forms.BooleanField(required=False, initial=True, label="Weather API")
    source_rivers = forms.BooleanField(required=False, initial=True, label="Rivers / Elevation")
    source_roads = forms.BooleanField(required=False, initial=True, label="Roads")

    def clean(self) -> dict[str, object]:
        cleaned = super().clean()
        if not cleaned:
            return cleaned

        start_dt = cleaned.get("start_datetime")
        end_dt = cleaned.get("end_datetime")
        if not start_dt or not end_dt:
            return cleaned

        if timezone.is_naive(start_dt):
            start_dt = timezone.make_aware(start_dt, timezone.get_current_timezone())
        if timezone.is_naive(end_dt):
            end_dt = timezone.make_aware(end_dt, timezone.get_current_timezone())

        cleaned["start_datetime"] = start_dt
        cleaned["end_datetime"] = end_dt

        now = timezone.now()
        if start_dt >= end_dt:
            raise forms.ValidationError("Start datetime must be earlier than end datetime.")

        if end_dt > now:
            raise forms.ValidationError("End datetime must be in the past for historical testing.")

        return cleaned
