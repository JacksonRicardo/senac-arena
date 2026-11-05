from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('arena', '0004_raffle')]
    operations = [
        migrations.AlterModelOptions(
            name='raffleparticipant',
            options={'ordering': ['name'], 'verbose_name': 'Participante da planilha',
                     'verbose_name_plural': 'Participantes da planilha'},
        ),
        migrations.AlterModelOptions(
            name='rafflewinner',
            options={'verbose_name': 'Sorteado', 'verbose_name_plural': 'Sorteados'},
        ),
    ]
