from __future__ import annotations

from django.db import models


class BacktestRun(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    area_slug = models.CharField(max_length=80)
    created_at = models.DateTimeField(auto_now_add=True)
    start_dt = models.DateTimeField()
    end_dt = models.DateTimeField()
    status = models.CharField(max_length=20, choices=Status, default=Status.PENDING)
    runtime_ms = models.FloatField(null=True, blank=True)
    notes = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        return f"BacktestRun#{self.pk} {self.area_slug} {self.status}"


class BacktestResult(models.Model):
    class ObjectType(models.TextChoices):
        CELL = "cell", "Cell"
        EDGE = "edge", "Road Edge"
        NODE = "node", "Road Node"

    run = models.ForeignKey(BacktestRun, on_delete=models.CASCADE, related_name="results")
    object_type = models.CharField(max_length=16, choices=ObjectType, db_index=True)
    object_id = models.CharField(max_length=120)
    risk_score = models.FloatField()
    timestamp = models.DateTimeField()
    extra_json = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        return f"{self.object_type}:{self.object_id} ({self.risk_score})"

    class Meta:
        ordering = ["-risk_score", "object_id"]
