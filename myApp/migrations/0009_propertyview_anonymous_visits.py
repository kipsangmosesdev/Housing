from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('myApp', '0008_alter_tokenwallet_tokens'),
    ]

    operations = [
        migrations.AlterField(
            model_name='propertyview',
            name='tenant',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to='myApp.tenant',
            ),
        ),
        migrations.AlterUniqueTogether(
            name='propertyview',
            unique_together=set(),
        ),
    ]
