from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="BacktestRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("area_slug", models.CharField(max_length=80)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("start_dt", models.DateTimeField()),
                ("end_dt", models.DateTimeField()),
                ("status", models.CharField(choices=[("pending", "Pending"), ("running", "Running"), ("completed", "Completed"), ("failed", "Failed")], default="pending", max_length=20)),
                ("runtime_ms", models.FloatField(blank=True, null=True)),
                ("notes", models.JSONField(blank=True, default=dict)),
            ],
        ),
        migrations.CreateModel(
            name="BacktestResult",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("object_type", models.CharField(choices=[("cell", "Cell"), ("edge", "Road Edge"), ("node", "Road Node")], db_index=True, max_length=16)),
                ("object_id", models.CharField(max_length=120)),
                ("risk_score", models.FloatField()),
                ("timestamp", models.DateTimeField()),
                ("extra_json", models.JSONField(blank=True, default=dict)),
                (
                    "run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="results",
                        to="testing.backtestrun",
                    ),
                ),
            ],
            options={"ordering": ["-risk_score", "object_id"]},
        ),
    ]
