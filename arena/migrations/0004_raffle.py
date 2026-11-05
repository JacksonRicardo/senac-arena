from django.db import migrations, models
import django.db.models.deletion


def create_lock(apps, schema_editor):
    apps.get_model('arena', 'RaffleLock').objects.using(schema_editor.connection.alias).create(pk=1)


class Migration(migrations.Migration):
    dependencies = [('arena', '0003_evaluator_evaluation_evaluator_and_more')]
    operations = [
        migrations.CreateModel(
            name='RaffleLock',
            fields=[('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                    ('version', models.PositiveBigIntegerField(default=0))],
        ),
        migrations.CreateModel(
            name='RaffleParticipant',
            fields=[('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                    ('identity', models.CharField(max_length=250, unique=True)),
                    ('name', models.CharField(max_length=250)),
                    ('unit', models.CharField(max_length=200)),
                    ('role', models.CharField(max_length=200)),
                    ('is_active', models.BooleanField(default=True))],
            options={'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='RaffleWinner',
            fields=[('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                    ('name', models.CharField(max_length=250)),
                    ('unit', models.CharField(max_length=200)),
                    ('request_id', models.UUIDField(unique=True)),
                    ('drawn_at', models.DateTimeField(auto_now_add=True)),
                    ('participant', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='winner', to='arena.raffleparticipant'))],
        ),
        migrations.RunPython(create_lock, migrations.RunPython.noop),
    ]
