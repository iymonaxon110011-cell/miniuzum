from django.contrib import admin

from .forms import PromoCodeForm
from .models import (
    CouponRedemption,
    Order,
    OrderItem,
    Product,
    ProductReview,
    Promotion,
    PromoCode,
    WishlistItem,
)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "brand", "category", "price", "is_ai_generated", "is_approved", "created_at")
    list_filter = ("is_approved", "is_ai_generated", "category", "brand")
    search_fields = ("name", "brand", "description")


@admin.register(WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    list_display = ("user", "product", "created_at")
    search_fields = ("user__username", "product__name", "product__brand")


@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    list_display = ("product", "user", "rating", "is_approved", "created_at")
    list_filter = ("is_approved", "rating", "created_at")
    list_editable = ("is_approved",)
    search_fields = ("product__name", "user__username", "comment")
    readonly_fields = ("product", "user", "rating", "comment", "created_at")


@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = (
        "title", "category", "product", "discount_type", "discount_value",
        "is_flash_sale", "starts_at", "ends_at", "is_active",
    )
    list_filter = ("is_active", "is_flash_sale", "category")
    search_fields = ("title", "subtitle", "product__name")


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    form = PromoCodeForm
    list_display = ("code", "discount_type", "discount_value", "minimum_order", "max_uses", "is_active", "ends_at")
    list_filter = ("is_active", "discount_type")
    search_fields = ("code",)
    readonly_fields = ("created_at",)


@admin.register(CouponRedemption)
class CouponRedemptionAdmin(admin.ModelAdmin):
    list_display = ("coupon", "user", "order", "redeemed_at")
    search_fields = ("coupon__code", "user__username", "order__id")
    readonly_fields = ("coupon", "user", "order", "redeemed_at")


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    readonly_fields = ("product_name", "unit_price", "quantity")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "customer_name", "phone", "total", "coupon_code", "cashback_amount", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("customer_name", "phone")
    readonly_fields = (
        "user", "customer_name", "phone", "address", "total", "status",
        "cashback_amount", "cashback_credited", "created_at",
    )
    inlines = (OrderItemInline,)