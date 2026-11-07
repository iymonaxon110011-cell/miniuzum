from decimal import Decimal

from django.db import migrations, models


def add_demo_products(apps, schema_editor):
    Product = apps.get_model("store", "Product")
    Product.objects.bulk_create(
        [
            Product(name="AirPods Pro 2 simsiz quloqchin", category="Elektronika", description="Shovqinni faol pasaytirish va tiniq ovoz bilan har kuni qulay tinglang.", price=Decimal("1899000"), old_price=Decimal("2299000"), image_url="https://images.unsplash.com/photo-1606220945770-b5b6c2c55bf1?auto=format&fit=crop&w=900&q=85"),
            Product(name="Minimalistik kundalik soat", category="Elektronika", description="Yengil korpus, nafis dizayn va kundalik obrazga mos uslub.", price=Decimal("459000"), old_price=Decimal("599000"), image_url="https://images.unsplash.com/photo-1523275335684-37898b6baf30?auto=format&fit=crop&w=900&q=85"),
            Product(name="Shahar uchun klassik krossovka", category="Kiyim", description="Yumshoq taglik va universal rang. Kun bo'yi qulaylik.", price=Decimal("379000"), old_price=Decimal("449000"), image_url="https://images.unsplash.com/photo-1542291026-7eec264c27ff?auto=format&fit=crop&w=900&q=85"),
            Product(name="Uy uchun ixcham espresso qahva mashinasi", category="Uy-ro'zg'or", description="Tonggi qahvangizni bir tugma bilan tayyorlang.", price=Decimal("1299000"), image_url="https://images.unsplash.com/photo-1517668808822-9ebb02f2a0e6?auto=format&fit=crop&w=900&q=85"),
            Product(name="Simsiz Bluetooth karnay", category="Elektronika", description="Kichik o'lcham, katta ovoz va istalgan joyda sevimli musiqa.", price=Decimal("329000"), old_price=Decimal("399000"), image_url="https://images.unsplash.com/photo-1608043152269-423dbba4e7e1?auto=format&fit=crop&w=900&q=85"),
            Product(name="Parvarish uchun yuz kremi", category="Go'zallik", description="Yengil tekstura va kundalik namlantirish uchun.", price=Decimal("99000"), image_url="https://images.unsplash.com/photo-1608248543803-ba4f8c70ae0b?auto=format&fit=crop&w=900&q=85"),
        ]
    )


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Product",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=140, verbose_name="Mahsulot nomi")),
                ("category", models.CharField(choices=[("Elektronika", "Elektronika"), ("Uy-ro'zg'or", "Uy-ro'zg'or"), ("Kiyim", "Kiyim"), ("Go'zallik", "Go'zallik"), ("Sport", "Sport"), ("Boshqa", "Boshqa")], default="Boshqa", max_length=40, verbose_name="Kategoriya")),
                ("description", models.TextField(blank=True, verbose_name="Tavsif")),
                ("price", models.DecimalField(decimal_places=0, max_digits=12, verbose_name="Narxi")),
                ("old_price", models.DecimalField(blank=True, decimal_places=0, max_digits=12, null=True, verbose_name="Eski narxi")),
                ("image_url", models.URLField(blank=True, verbose_name="Rasm havolasi")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Qo'shilgan vaqt")),
            ],
            options={"verbose_name": "Mahsulot", "verbose_name_plural": "Mahsulotlar", "ordering": ["-created_at"]},
        ),
        migrations.RunPython(add_demo_products, migrations.RunPython.noop),
    ]