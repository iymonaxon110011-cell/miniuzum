from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0008_alter_product_category"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="is_ai_generated",
            field=models.BooleanField(default=False, verbose_name="Avtomatik taklif"),
        ),
        migrations.AddField(
            model_name="product",
            name="is_approved",
            field=models.BooleanField(default=True, verbose_name="Saytda ko‘rsatish"),
        ),
        migrations.CreateModel(
            name="DailyProductSuggestionRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("generated_for", models.DateField(unique=True, verbose_name="Taklif yaratilgan sana")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Yaratilgan vaqt")),
            ],
            options={
                "verbose_name": "Kunlik mahsulot taklifi",
                "verbose_name_plural": "Kunlik mahsulot takliflari",
            },
        ),
    ]
