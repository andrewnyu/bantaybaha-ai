from django.contrib import admin

from .models import EvacuationCenter


@admin.register(EvacuationCenter)
class EvacuationCenterAdmin(admin.ModelAdmin):
    list_display = ("name", "latitude", "longitude", "capacity")
    search_fields = ("name",)
