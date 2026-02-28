from __future__ import annotations

from django.shortcuts import render
from django.utils import timezone

from .forms import KNOWN_STORM_END, KNOWN_STORM_START, TestingBacktestForm
from .services import BacktestInputError, BacktestRateLimitError, run_backtest
from .utils import is_testing_tab_enabled


def _default_form_initial() -> dict[str, object]:
    local_tz = timezone.get_current_timezone()
    return {
        "location_slug": "negros-island",
        "start_datetime": timezone.make_aware(KNOWN_STORM_START, local_tz),
        "end_datetime": timezone.make_aware(KNOWN_STORM_END, local_tz),
        "source_weather": True,
        "source_rivers": True,
        "source_roads": True,
    }


def _cleaned_sources(form_data: dict[str, object]) -> dict[str, bool]:
    return {
        "weather": bool(form_data.get("source_weather")),
        "rivers": bool(form_data.get("source_rivers")),
        "roads": bool(form_data.get("source_roads")),
    }


def testing_page(request):
    can_show_tab = is_testing_tab_enabled()
    result = None
    form = TestingBacktestForm(request.POST or None, initial=_default_form_initial())

    if request.method == "POST":
        if form.is_valid():
            sources = _cleaned_sources(form.cleaned_data)
            try:
                result = run_backtest(
                    area_slug=form.cleaned_data["location_slug"],
                    start_dt=form.cleaned_data["start_datetime"],
                    end_dt=form.cleaned_data["end_datetime"],
                    sources=sources,
                )
            except BacktestRateLimitError as exc:
                form.add_error(None, str(exc))
            except BacktestInputError as exc:
                form.add_error(None, str(exc))

    return render(
        request,
        "testing/index.html",
        {
            "show_testing_tab": can_show_tab,
            "form": form,
            "result": result,
            "top_results": result.top_results if result else [],
            "run": result.run if result else None,
            "runtime_ms": result.runtime_ms if result else None,
            "nodes_processed": result.nodes_processed if result else 0,
            "edges_processed": result.edges_processed if result else 0,
            "flooded_count": result.flooded_count if result else 0,
        },
    )
