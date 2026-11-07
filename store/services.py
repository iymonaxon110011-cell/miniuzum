from django.db import transaction
from django.utils import timezone

from .models import DailyProductSuggestionRun, Product


@transaction.atomic
def generate_daily_product_suggestion(today=None):
    today = today or timezone.localdate()
    if DailyProductSuggestionRun.objects.filter(generated_for=today).exists():
        return None

    source_products = list(
        Product.objects.filter(is_approved=True)
        .only("name", "brand", "category", "color", "season", "price")
        .order_by("pk")
    )
    if not source_products:
        return None

    _, created = DailyProductSuggestionRun.objects.get_or_create(generated_for=today)
    if not created:
        return None

    source = source_products[today.toordinal() % len(source_products)]
    date_label = today.strftime("%d.%m")
    return Product.objects.create(
        name=f"{source.name} — yangi taklif {date_label}",
        brand=source.brand,
        category=source.category,
        color=source.color,
        season=source.season,
        description=(
            f"Bu {source.category} turkumidagi “{source.name}” mahsulotiga asoslangan "
            "avtomatik demo taklif. Bu haqiqiy yangi mahsulot emas. Saytga chiqarishdan "
            "oldin nomi, narxi, rasmi va tavsifini tekshirib tahrirlang."
        ),
        price=source.price,
        is_ai_generated=True,
        is_approved=False,
    )
