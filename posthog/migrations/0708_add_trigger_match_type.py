# Generated by Django 4.2.18 on 2025-04-09 13:03

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("posthog", "0707_file_system_shortcut"),
    ]

    operations = [
        migrations.AddField(
            model_name="team",
            name="session_recording_trigger_match_type_config",
            field=models.CharField(blank=True, max_length=24, null=True),
        ),
    ]
