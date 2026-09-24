from django.db import migrations


# Backfill: existing users (who already have a settings row) have been using
# the product — they should not be interrupted by the first-run tour. Only
# brand-new accounts (where ``onboarding_done`` keeps its ``False`` default)
# see it. A ``RunPython`` makes the intent explicit and reversible.


def mark_existing_users_onboarded(apps, schema_editor):
    UserSettings = apps.get_model("tasks", "UserSettings")
    UserSettings.objects.update(onboarding_done=True)


def mark_onboarded_unset(apps, schema_editor):
    # Reverse: restore the pre-field state for every row.
    UserSettings = apps.get_model("tasks", "UserSettings")
    UserSettings.objects.update(onboarding_done=False)


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0006_usersettings_onboarding_done'),
    ]

    operations = [
        migrations.RunPython(
            mark_existing_users_onboarded,
            reverse_code=mark_onboarded_unset,
        ),
    ]