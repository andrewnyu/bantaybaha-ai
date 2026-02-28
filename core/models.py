from django.db import models


class EvacuationCenter(models.Model):
    name = models.CharField(max_length=150)
    latitude = models.FloatField()
    longitude = models.FloatField()
    capacity = models.PositiveIntegerField()

    def __str__(self) -> str:
        return self.name
