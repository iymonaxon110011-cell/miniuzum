from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models


class Product(models.Model):
    CATEGORY_CHOICES = [
        ("Elektronika", "Elektronika"),
        ("Uy-ro'zg'or", "Uy-ro'zg'or"),
        ("Kiyim", "Kiyim"),
        ("Go'zallik", "Go'zallik"),
        ("Sport", "Sport"),
        ("Boshqa", "Boshqa"),
    ]
    COLOR_CHOICES = [
        ("brown", "Jigarrang"),
        ("red", "Qizil"),
        ("green", "Yashil"),
        ("khaki", "Xaki"),
        ("pink", "Pushti"),
        ("yellow", "Sariq"),
        ("black", "Qora"),
        ("white", "Oq"),
        ("blue", "Ko‘k"),
        ("gray", "Kulrang"),
        ("purple", "Binafsha"),
        ("navy", "To‘q ko‘k"),
        ("beige", "Bej"),
        ("dark_green", "To‘q yashil"),
        ("burgundy", "To‘q qizil"),
        ("orange", "To‘q sariq"),
    ]
    SEASON_CHOICES = [
        ("spring", "Bahor"),
        ("winter", "Qish"),
        ("summer", "Yoz"),
        ("autumn", "Kuz"),
    ]

    name = models.CharField("Mahsulot nomi", max_length=140)
    brand = models.CharField("Brend", max_length=80, blank=True)
    category = models.CharField("Kategoriya", max_length=40, default="Boshqa")
    color = models.CharField("Rang", max_length=16, choices=COLOR_CHOICES, blank=True)
    season = models.CharField("Mavsum", max_length=10, choices=SEASON_CHOICES, blank=True)
    description = models.TextField("Tavsif", blank=True)
    price = models.DecimalField("Narxi", max_digits=12, decimal_places=0)
    old_price = models.DecimalField("Eski narxi", max_digits=12, decimal_places=0, blank=True, null=True)
    image_url = models.URLField("Rasm havolasi", blank=True)
    is_ai_generated = models.BooleanField("Avtomatik taklif", default=False)
    is_approved = models.BooleanField("Saytda ko‘rsatish", default=True)
    created_at = models.DateTimeField("Qo'shilgan vaqt", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Mahsulot"
        verbose_name_plural = "Mahsulotlar"

    def __str__(self):
        return self.name

    @property
    def discount_percent(self):
        if not self.old_price or self.old_price <= self.price:
            return 0
        return round((self.old_price - self.price) / self.old_price * 100)


class DailyProductSuggestionRun(models.Model):
    generated_for = models.DateField("Taklif yaratilgan sana", unique=True)
    created_at = models.DateTimeField("Yaratilgan vaqt", auto_now_add=True)

    class Meta:
        verbose_name = "Kunlik mahsulot taklifi"
        verbose_name_plural = "Kunlik mahsulot takliflari"

    def __str__(self):
        return str(self.generated_for)


class WishlistItem(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wishlist_items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="wishlisted_by")
    created_at = models.DateTimeField("Qo‘shilgan vaqt", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "product"], name="unique_user_wishlist_product"),
        ]
        verbose_name = "Sevimli mahsulot"
        verbose_name_plural = "Sevimli mahsulotlar"

    def __str__(self):
        return f"{self.user} — {self.product}"


class Promotion(models.Model):
    DISCOUNT_TYPE_CHOICES = [
        ("percent", "Foiz"),
        ("fixed", "Belgilangan summa"),
    ]

    title = models.CharField("Sarlavha", max_length=120)
    subtitle = models.CharField("Qisqa matn", max_length=180, blank=True)
    category = models.CharField("Mahsulot kategoriyasi", max_length=40, choices=Product.CATEGORY_CHOICES, blank=True)
    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="promotions",
        verbose_name="Maqsadli mahsulot",
    )
    image_url = models.URLField("Rasm manzili")
    discount_label = models.CharField("Chegirma yozuvi", max_length=24, blank=True)
    discount_type = models.CharField("Chegirma turi", max_length=8, choices=DISCOUNT_TYPE_CHOICES, default="percent")
    discount_value = models.DecimalField("Chegirma miqdori", max_digits=10, decimal_places=2, default=0)
    starts_at = models.DateTimeField("Boshlanish vaqti", blank=True, null=True)
    ends_at = models.DateTimeField("Tugash vaqti", blank=True, null=True)
    is_flash_sale = models.BooleanField("Flash sale", default=False)
    is_active = models.BooleanField("Faol", default=True)
    created_at = models.DateTimeField("Qo‘shilgan vaqt", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Aksiya"
        verbose_name_plural = "Aksiyalar"

    def clean(self):
        errors = {}
        if self.discount_value < 0:
            errors["discount_value"] = "Chegirma manfiy bo‘lishi mumkin emas."
        elif self.discount_type == "percent" and self.discount_value > 100:
            errors["discount_value"] = "Foizli chegirma 100% dan oshmasligi kerak."
        if self.discount_value and not (self.product_id or self.category):
            errors["product"] = "Chegirma uchun mahsulot yoki turkum tanlang."
        if self.starts_at and self.ends_at and self.starts_at >= self.ends_at:
            errors["ends_at"] = "Tugash vaqti boshlanish vaqtidan keyin bo‘lishi kerak."
        if self.is_flash_sale:
            if not self.ends_at:
                errors["ends_at"] = "Flash sale uchun tugash vaqtini kiriting."
            if not self.discount_value:
                errors["discount_value"] = "Flash sale uchun chegirma miqdorini kiriting."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.title


class PromoCode(models.Model):
    DISCOUNT_TYPE_CHOICES = Promotion.DISCOUNT_TYPE_CHOICES

    code = models.CharField("Promokod", max_length=32, unique=True)
    discount_type = models.CharField("Chegirma turi", max_length=8, choices=DISCOUNT_TYPE_CHOICES)
    discount_value = models.DecimalField("Chegirma miqdori", max_digits=10, decimal_places=2)
    minimum_order = models.DecimalField("Minimal buyurtma", max_digits=12, decimal_places=0, default=0)
    starts_at = models.DateTimeField("Boshlanish vaqti", blank=True, null=True)
    ends_at = models.DateTimeField("Tugash vaqti", blank=True, null=True)
    max_uses = models.PositiveIntegerField("Umumiy foydalanish limiti", blank=True, null=True)
    is_active = models.BooleanField("Faol", default=True)
    created_at = models.DateTimeField("Yaratilgan vaqt", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Promokod"
        verbose_name_plural = "Promokodlar"

    def clean(self):
        errors = {}
        if self.discount_value <= 0:
            errors["discount_value"] = "Chegirma miqdori noldan katta bo‘lishi kerak."
        elif self.discount_type == "percent" and self.discount_value > 100:
            errors["discount_value"] = "Foizli chegirma 100% dan oshmasligi kerak."
        if self.minimum_order < 0:
            errors["minimum_order"] = "Minimal buyurtma manfiy bo‘lishi mumkin emas."
        if self.starts_at and self.ends_at and self.starts_at >= self.ends_at:
            errors["ends_at"] = "Tugash vaqti boshlanish vaqtidan keyin bo‘lishi kerak."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)


class CouponRedemption(models.Model):
    coupon = models.ForeignKey(PromoCode, on_delete=models.PROTECT, related_name="redemptions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="coupon_redemptions")
    order = models.OneToOneField("Order", on_delete=models.CASCADE, related_name="coupon_redemption")
    redeemed_at = models.DateTimeField("Foydalanilgan vaqt", auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["coupon", "user"], name="unique_coupon_redemption_per_user"),
        ]
        verbose_name = "Promokod ishlatilishi"
        verbose_name_plural = "Promokod ishlatilishlari"


class Order(models.Model):
    STATUS_CHOICES = [
        ("new", "Yangi"),
        ("processing", "Jarayonda"),
        ("completed", "Yakunlangan"),
        ("cancelled", "Bekor qilingan"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="store_orders",
        blank=True,
        null=True,
        verbose_name="Foydalanuvchi",
    )
    customer_name = models.CharField("Buyurtmachi", max_length=120)
    phone = models.CharField("Telefon", max_length=30)
    address = models.CharField("Yetkazish manzili", max_length=255)
    total = models.DecimalField("Jami", max_digits=12, decimal_places=0)
    subtotal = models.DecimalField("Chegirmagacha jami", max_digits=12, decimal_places=0, default=0)
    discount_amount = models.DecimalField("Chegirma", max_digits=12, decimal_places=0, default=0)
    coupon = models.ForeignKey(PromoCode, on_delete=models.SET_NULL, blank=True, null=True, related_name="orders")
    coupon_code = models.CharField("Qo‘llangan promokod", max_length=32, blank=True)
    cashback_amount = models.DecimalField("Keshbek", max_digits=12, decimal_places=0, default=0)
    cashback_credited = models.BooleanField("Keshbek hamyonga tushgan", default=False)
    status = models.CharField("Holati", max_length=16, choices=STATUS_CHOICES, default="new")
    created_at = models.DateTimeField("Buyurtma vaqti", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Buyurtma"
        verbose_name_plural = "Buyurtmalar"

    def __str__(self):
        return f"Buyurtma #{self.pk} — {self.customer_name}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items", verbose_name="Buyurtma")
    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        related_name="order_items",
        blank=True,
        null=True,
        verbose_name="Mahsulot",
    )
    product_name = models.CharField("Mahsulot nomi", max_length=140)
    unit_price = models.DecimalField("Bir dona narxi", max_digits=12, decimal_places=0)
    quantity = models.PositiveIntegerField("Miqdori")

    class Meta:
        verbose_name = "Buyurtma mahsuloti"
        verbose_name_plural = "Buyurtma mahsulotlari"

    def __str__(self):
        return f"{self.product_name} × {self.quantity}"

    @property
    def line_total(self):
        return self.unit_price * self.quantity


class ProductReview(models.Model):
    RATING_CHOICES = [(value, str(value)) for value in range(1, 6)]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews", verbose_name="Mahsulot")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="product_reviews", verbose_name="Xaridor")
    rating = models.PositiveSmallIntegerField("Baho", choices=RATING_CHOICES)
    comment = models.TextField("Izoh", max_length=1000)
    is_approved = models.BooleanField("Tasdiqlangan", default=False)
    created_at = models.DateTimeField("Yuborilgan vaqt", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "product"], name="unique_user_product_review"),
        ]
        verbose_name = "Mahsulot sharhi"
        verbose_name_plural = "Mahsulot sharhlari"

    def __str__(self):
        return f"{self.product} — {self.user} ({self.rating}/5)"


class Wallet(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="store_wallet")
    balance = models.DecimalField("Balans", max_digits=12, decimal_places=0, default=0)
    card_last4 = models.CharField("Karta oxirgi raqamlari", max_length=4, blank=True)
    updated_at = models.DateTimeField("Yangilangan vaqt", auto_now=True)

    def __str__(self):
        return f"{self.user} — {self.balance} so‘m"


class TopUpRequest(models.Model):
    STATUS_CHOICES = [
        ("pending", "Ko‘rib chiqilmoqda"),
        ("approved", "Tasdiqlandi"),
        ("rejected", "Rad etildi"),
    ]

    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="top_up_requests")
    amount = models.DecimalField("Summa", max_digits=12, decimal_places=0, validators=[MinValueValidator(1000)])
    status = models.CharField("Holati", max_length=12, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField("Yuborilgan vaqt", auto_now_add=True)
    reviewed_at = models.DateTimeField("Ko‘rib chiqilgan vaqt", blank=True, null=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="reviewed_top_up_requests",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.wallet.user} — {self.amount} so‘m ({self.get_status_display()})"


class CardChangeRequest(models.Model):
    ACTION_CHOICES = [
        ("add", "Karta qo‘shish"),
        ("remove", "Kartani o‘chirish"),
    ]
    STATUS_CHOICES = TopUpRequest.STATUS_CHOICES

    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="card_change_requests")
    action = models.CharField("Amal", max_length=8, choices=ACTION_CHOICES)
    card_last4 = models.CharField("Karta oxirgi raqamlari", max_length=4)
    status = models.CharField("Holati", max_length=12, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField("Yuborilgan vaqt", auto_now_add=True)
    reviewed_at = models.DateTimeField("Ko‘rib chiqilgan vaqt", blank=True, null=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="reviewed_card_change_requests",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["wallet"],
                condition=models.Q(status="pending"),
                name="unique_pending_card_change_per_wallet",
            ),
        ]
        verbose_name = "Karta o‘zgartirish so‘rovi"
        verbose_name_plural = "Karta o‘zgartirish so‘rovlari"

    def __str__(self):
        return f"{self.wallet.user} — {self.get_action_display()} ({self.get_status_display()})"
  