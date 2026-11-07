from datetime import date, datetime, time
from difflib import SequenceMatcher
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import login
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, F, Max, Min, Q, Sum
from django.db.models.functions import TruncMonth
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from .forms import (
    CardNumberForm,
    CheckoutForm,
    LoginForm,
    ProductForm,
    ProductReviewForm,
    PromotionForm,
    PromoCodeForm,
    RegisterForm,
    TopUpForm,
)
from .models import (
    CardChangeRequest,
    CouponRedemption,
    Order,
    OrderItem,
    Product,
    ProductReview,
    Promotion,
    PromoCode,
    TopUpRequest,
    Wallet,
    WishlistItem,
)

CASHBACK_PERCENT = Decimal("5")


def page_not_found(request, exception):
    return render(request, "store/404.html", status=404)


def _product_category_choices():
    categories = list(Product.CATEGORY_CHOICES)
    known_categories = {value for value, _ in categories}
    custom_categories = (
        Product.objects.filter(is_approved=True)
        .order_by()
        .values_list("category", flat=True)
        .distinct()
    )
    categories.extend(
        (category, category)
        for category in sorted(set(custom_categories) - known_categories, key=str.casefold)
        if category
    )
    return categories


def _correct_search_query(query, products):
    vocabulary = set()
    for name, brand, category in products.order_by().values_list("name", "brand", "category"):
        vocabulary.update(
            word.casefold()
            for value in (name, brand, category)
            for word in re.findall(r"\w+", value or "")
            if len(word) >= 4
        )

    def correct_word(match):
        word = match.group()
        normalized = word.casefold()
        if len(normalized) < 4:
            return word

        candidates = sorted(
            (
                (SequenceMatcher(None, normalized, candidate).ratio(), candidate)
                for candidate in vocabulary
                if candidate != normalized and abs(len(candidate) - len(normalized)) <= 2
            ),
            reverse=True,
        )
        if not candidates or candidates[0][0] < 0.78:
            return word
        if len(candidates) > 1 and candidates[0][0] - candidates[1][0] < 0.03:
            return word
        return candidates[0][1]

    return re.sub(r"\w+", correct_word, query)


def _active_promotions(now=None):
    now = now or timezone.now()
    return Promotion.objects.filter(is_active=True).filter(
        Q(starts_at__isnull=True) | Q(starts_at__lte=now),
        Q(ends_at__isnull=True) | Q(ends_at__gt=now),
    )


def _apply_marketing_prices(products, now=None):
    products = list(products)
    if not products:
        return products

    product_ids = [product.pk for product in products]
    categories = {product.category for product in products}
    campaigns = _active_promotions(now).filter(discount_value__gt=0).filter(
        Q(product_id__in=product_ids) | Q(product__isnull=True, category__in=categories)
    )
    campaigns_by_product = {}
    for campaign in campaigns:
        key = ("product", campaign.product_id) if campaign.product_id else ("category", campaign.category)
        campaigns_by_product.setdefault(key, []).append(campaign)

    for product in products:
        current_price = product.price
        original_price = product.old_price if product.old_price and product.old_price > current_price else None
        active_price = current_price
        if original_price is None:
            matching_campaigns = campaigns_by_product.get(("product", product.pk), [])
            if not matching_campaigns:
                matching_campaigns = campaigns_by_product.get(("category", product.category), [])
            for campaign in matching_campaigns:
                if campaign.discount_type == "percent":
                    candidate = current_price * (Decimal("1") - campaign.discount_value / Decimal("100"))
                else:
                    candidate = current_price - campaign.discount_value
                candidate = max(Decimal("0"), candidate).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
                active_price = min(active_price, candidate)
            if active_price < current_price:
                original_price = current_price

        product.marketing_price = active_price
        product.marketing_old_price = original_price
        product.marketing_discount_percent = (
            round((original_price - active_price) * 100 / original_price)
            if original_price and original_price > 0 else 0
        )
        product.marketing_discounted = bool(original_price and active_price < original_price)
    return products


def _recommended_products(category, exclude_ids=()):
    if not category:
        return []
    products = Product.objects.filter(is_approved=True, category=category).exclude(pk__in=exclude_ids)
    products = products.annotate(order_count=Count("order_items")).order_by("-order_count", "-created_at")[:4]
    return _apply_marketing_prices(products)


def _coupon_discount(coupon, subtotal):
    if coupon.discount_type == "percent":
        amount = subtotal * coupon.discount_value / Decimal("100")
    else:
        amount = coupon.discount_value
    return min(subtotal, amount).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _coupon_error(coupon, user, subtotal, items, now=None):
    now = now or timezone.now()
    if not coupon.is_active:
        return "Bu promokod hozir faol emas."
    if coupon.starts_at and coupon.starts_at > now:
        return "Bu promokod hali kuchga kirmagan."
    if coupon.ends_at and coupon.ends_at <= now:
        return "Bu promokodning amal qilish muddati tugagan."
    if subtotal < coupon.minimum_order:
        return f"Promokod uchun buyurtma kamida {coupon.minimum_order:,.0f} so‘m bo‘lishi kerak."
    if coupon.redemptions.filter(user=user).exists():
        return "Bu promokoddan avval foydalangansiz."
    if coupon.max_uses is not None and coupon.redemptions.count() >= coupon.max_uses:
        return "Bu promokod uchun foydalanish limiti tugagan."
    if any(item["is_discounted"] for item in items):
        return "Promokod mahsulot chegirmalari bilan birga qo‘llanmaydi."
    return ""


def register(request):
    if request.user.is_authenticated:
        return redirect("product_list")

    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Hisobingiz muvaffaqiyatli yaratildi.")
        return redirect("product_list")

    return render(
        request,
        "store/auth_form.html",
        {
            "form": form,
            "is_register": True,
        },
    )


def product_list(request):
    products = Product.objects.filter(is_approved=True)
    query = request.GET.get("q", "").strip()
    category = request.GET.get("category", "")
    brand = request.GET.get("brand", "").strip()
    sort = request.GET.get("sort", "")
    selected_colors = request.GET.getlist("color")
    selected_seasons = request.GET.getlist("season") if category == "Kiyim" else []
    price_bounds = products.aggregate(min_price=Min("price"), max_price=Max("price"))
    price_range_min = price_bounds["min_price"] or Decimal("0")
    price_range_max = price_bounds["max_price"] or Decimal("0")

    def parse_price_filter(parameter):
        raw_value = request.GET.get(parameter, "").strip()
        if not raw_value:
            return None
        try:
            price = Decimal(raw_value)
        except InvalidOperation:
            messages.error(request, "Narxni to‘g‘ri kiriting.")
            return None
        if not price.is_finite() or price < 0:
            messages.error(request, "Narx manfiy bo‘lishi mumkin emas.")
            return None
        if price > Decimal("999999999999"):
            messages.error(request, "Narx 999 999 999 999 so‘mdan oshmasligi kerak.")
            return None
        return price

    selected_min_price = parse_price_filter("min_price")
    selected_max_price = parse_price_filter("max_price")
    if selected_min_price is not None and selected_max_price is not None and selected_min_price > selected_max_price:
        messages.error(request, "Boshlang‘ich narx yakuniy narxdan katta bo‘lishi mumkin emas.")
        selected_min_price = None
        selected_max_price = None

    if category:
        products = products.filter(category=category)
    if brand:
        products = products.filter(brand__icontains=brand)
    if selected_colors:
        products = products.filter(color__in=selected_colors)
    if selected_seasons and category == "Kiyim":
        products = products.filter(season__in=selected_seasons)
    if selected_min_price is not None or selected_max_price is not None:
        price_candidates = _apply_marketing_prices(products)
        if selected_min_price is not None:
            price_candidates = [
                product for product in price_candidates
                if product.marketing_price >= selected_min_price
            ]
        if selected_max_price is not None:
            price_candidates = [
                product for product in price_candidates
                if product.marketing_price <= selected_max_price
            ]
        products = products.filter(pk__in=[product.pk for product in price_candidates])

    search_suggestions = list(
        products.order_by("-created_at").values_list("name", flat=True)[:30]
    )
    search_corrected_query = ""
    if query:
        search_fields = Q(name__icontains=query) | Q(brand__icontains=query) | Q(description__icontains=query)
        matching_products = products.filter(search_fields)
        if matching_products.exists():
            products = matching_products
        else:
            corrected_query = _correct_search_query(query, Product.objects.filter(is_approved=True))
            if corrected_query != query:
                corrected_products = products.filter(
                    Q(name__icontains=corrected_query)
                    | Q(brand__icontains=corrected_query)
                    | Q(description__icontains=corrected_query)
                )
                if corrected_products.exists():
                    products = corrected_products
                    search_corrected_query = corrected_query
                else:
                    products = matching_products
            else:
                products = matching_products

    if sort == "price_asc":
        products = products.order_by("price")
    elif sort == "price_desc":
        products = products.order_by("-price")

    favorite_product_ids = set()
    if request.user.is_authenticated:
        favorite_product_ids = set(
            WishlistItem.objects.filter(user=request.user).values_list("product_id", flat=True)
        )

    catalog_products = _apply_marketing_prices(products)
    product_queryset = products.filter(pk__in=[product.pk for product in catalog_products])
    if sort == "price_asc":
        catalog_products.sort(key=lambda product: product.marketing_price)
    elif sort == "price_desc":
        catalog_products.sort(key=lambda product: product.marketing_price, reverse=True)
    recent_ids = request.session.get("recently_viewed_products", [])
    recent_products = list(
        Product.objects.filter(pk__in=recent_ids, is_approved=True).only("pk", "category")
    )
    recent_by_id = {product.pk: product for product in recent_products}
    recent_category = next(
        (recent_by_id[pk].category for pk in recent_ids if pk in recent_by_id),
        "",
    )
    recommendation_excluded_ids = set(recent_ids)
    has_catalog_filters = bool(
        query or category or brand or sort or selected_colors
        or selected_min_price is not None or selected_max_price is not None
    )
    if catalog_products and not recent_category and not has_catalog_filters:
        recent_category = catalog_products[0].category
    recommendations = (
        _recommended_products(recent_category, recommendation_excluded_ids)
        if not has_catalog_filters else []
    )

    active_promotions = _active_promotions().select_related("product")
    flash_sale_products = []
    for promotion in active_promotions.filter(is_flash_sale=True, discount_value__gt=0):
        if promotion.product_id:
            flash_sale_products.extend(
                Product.objects.filter(pk=promotion.product_id, is_approved=True)
            )
        elif promotion.category:
            flash_sale_products.extend(
                Product.objects.filter(category=promotion.category, is_approved=True)[:8]
            )
    unique_flash_products = {product.pk: product for product in flash_sale_products}
    flash_sale_products = _apply_marketing_prices(unique_flash_products.values())

    return render(
        request,
        "store/product_list.html",
        {
            "products": product_queryset,
            "catalog_products": catalog_products,
            "query": query,
            "search_corrected_query": search_corrected_query,
            "search_suggestions": search_suggestions,
            "selected_category": category,
            "selected_brand": brand,
            "selected_sort": sort,
            "selected_colors": selected_colors,
            "selected_seasons": selected_seasons,
            "selected_min_price": selected_min_price,
            "selected_max_price": selected_max_price,
            "price_range_min": price_range_min,
            "price_range_max": price_range_max,
            "colors": Product.COLOR_CHOICES,
            "seasons": Product.SEASON_CHOICES,
            "favorite_product_ids": favorite_product_ids,
            "next_url": request.get_full_path(),
            "categories": _product_category_choices(),
            "promotions": active_promotions[:5],
            "flash_sale_products": flash_sale_products,
            "recommendations": recommendations,
            "recommendation_category": recent_category,
        },
    )


def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk, is_approved=True)
    _apply_marketing_prices([product])
    recent_ids = request.session.get("recently_viewed_products", [])
    request.session["recently_viewed_products"] = [product.pk] + [
        recent_id for recent_id in recent_ids if recent_id != product.pk
    ][:4]
    recommendations = _recommended_products(product.category, [product.pk])
    is_favorite = request.user.is_authenticated and WishlistItem.objects.filter(user=request.user, product=product).exists()
    review_form = ProductReviewForm()
    user_review = None
    can_review = False

    if request.user.is_authenticated:
        user_review = ProductReview.objects.filter(product=product, user=request.user).first()
        can_review = (
            user_review is None
            and OrderItem.objects.filter(
                product=product,
                order__user=request.user,
                order__status="completed",
            ).exists()
        )

    if request.method == "POST":
        if not request.user.is_authenticated:
            messages.info(request, "Sharh qoldirish uchun avval hisobingizga kiring.")
            return redirect(f"{reverse('login')}?next={reverse('product_detail', args=[product.pk])}%23reviews")
        if not can_review:
            messages.error(request, "Sharhni faqat xaridi yakunlangan foydalanuvchi qoldira oladi.")
            return redirect(f"{reverse('product_detail', args=[product.pk])}#reviews")

        review_form = ProductReviewForm(request.POST)
        if review_form.is_valid():
            review, created = ProductReview.objects.get_or_create(
                product=product,
                user=request.user,
                defaults={
                    "rating": review_form.cleaned_data["rating"],
                    "comment": review_form.cleaned_data["comment"],
                },
            )
            if created:
                messages.success(request, "Sharhingiz yuborildi va admin tekshiruvini kutmoqda.")
            else:
                messages.info(request, "Bu mahsulot uchun sharh qoldirgansiz.")
            return redirect(f"{reverse('product_detail', args=[product.pk])}#reviews")

    reviews = ProductReview.objects.filter(product=product, is_approved=True).select_related("user")
    review_summary = reviews.aggregate(average=Avg("rating"), count=Count("id"))
    return render(request, "store/product_detail.html", {
        "product": product,
        "is_favorite": is_favorite,
        "next_url": request.get_full_path(),
        "reviews": reviews,
        "review_count": review_summary["count"],
        "review_average": review_summary["average"],
        "review_form": review_form,
        "can_review": can_review,
        "user_review": user_review,
        "rating_values": range(1, 6),
        "recommendations": recommendations,
    })


@login_required
def wishlist(request):
    products = Product.objects.filter(wishlisted_by__user=request.user, is_approved=True)
    products = _apply_marketing_prices(products)
    return render(request, "store/wishlist.html", {"products": products})


@login_required
@require_POST
def wishlist_toggle(request, pk):
    product = get_object_or_404(Product, pk=pk, is_approved=True)
    item, created = WishlistItem.objects.get_or_create(user=request.user, product=product)
    if not created:
        item.delete()
        messages.success(request, f"{product.name} sevimlilardan olib tashlandi.")
    else:
        messages.success(request, f"{product.name} sevimlilarga qo‘shildi.")

    next_url = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        next_url = reverse("wishlist")
    return redirect(next_url)


def _is_admin(user):
    return user.is_staff


def _create_card_change_request(wallet, action, card_last4):
    try:
        with transaction.atomic():
            CardChangeRequest.objects.create(
                wallet=wallet,
                action=action,
                card_last4=card_last4,
            )
    except IntegrityError:
        if wallet.card_change_requests.filter(status="pending").exists():
            return False
        raise
    return True


@user_passes_test(_is_admin)
def dashboard(request):
    product_form = ProductForm()
    promotion_form = PromotionForm()
    promo_code_form = PromoCodeForm()
    editing_product_id = None
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "save_product":
            product_id = request.POST.get("product_id")
            instance = get_object_or_404(Product, pk=product_id) if product_id else None
            product_form = ProductForm(request.POST, request.FILES, instance=instance)
            if product_form.is_valid():
                product = product_form.save()
                verb = "yangilandi" if instance else "qo‘shildi"
                messages.success(request, f"{product.name} {verb}.")
                section = "ai-products" if product.is_ai_generated and not product.is_approved else "products"
                return redirect(f"{reverse('dashboard')}#{section}")
            editing_product_id = instance.pk if instance else None
        elif action == "save_promotion":
            promotion_form = PromotionForm(request.POST, request.FILES)
            if promotion_form.is_valid():
                promotion = promotion_form.save()
                messages.success(request, f"{promotion.title} aksiyasi qo‘shildi.")
                return redirect(f"{reverse('dashboard')}#promotions")
        elif action == "save_promo_code":
            promo_code_form = PromoCodeForm(request.POST)
            if promo_code_form.is_valid():
                promo_code = promo_code_form.save()
                messages.success(request, f"{promo_code.code} promokodi saqlandi.")
                return redirect(f"{reverse('dashboard')}#promo-codes")
        elif action == "toggle_promo_code":
            promo_code = get_object_or_404(PromoCode, pk=request.POST.get("promo_code_id"))
            promo_code.is_active = not promo_code.is_active
            promo_code.save(update_fields=["is_active"])
            state = "faollashtirildi" if promo_code.is_active else "to‘xtatildi"
            messages.success(request, f"{promo_code.code} promokodi {state}.")
            return redirect(f"{reverse('dashboard')}#promo-codes")
        elif action == "delete_promotion":
            promotion = get_object_or_404(Promotion, pk=request.POST.get("promotion_id"))
            title = promotion.title
            promotion.delete()
            messages.success(request, f"{title} aksiyasi o‘chirildi.")
            return redirect(f"{reverse('dashboard')}#promotions")
        elif action == "delete_product":
            product = get_object_or_404(Product, pk=request.POST.get("product_id"))
            name = product.name
            product.delete()
            messages.success(request, f"{name} o‘chirildi.")
            return redirect(f"{reverse('dashboard')}#products")
        elif action in ("approve_ai_product", "reject_ai_product"):
            product = get_object_or_404(
                Product,
                pk=request.POST.get("product_id"),
                is_ai_generated=True,
                is_approved=False,
            )
            if action == "approve_ai_product":
                product.is_approved = True
                product.save(update_fields=["is_approved"])
                messages.success(request, f"{product.name} katalogda ko‘rsatishga tasdiqlandi.")
            else:
                name = product.name
                product.delete()
                messages.success(request, f"{name} taklifi rad etildi.")
            return redirect(f"{reverse('dashboard')}#ai-products")
        elif action in ("approve_review", "reject_review"):
            review = get_object_or_404(
                ProductReview.objects.select_related("product"),
                pk=request.POST.get("review_id"),
                is_approved=False,
            )
            if action == "approve_review":
                review.is_approved = True
                review.save(update_fields=["is_approved"])
                messages.success(request, f"{review.product.name} mahsuloti sharhi tasdiqlandi.")
            else:
                review.delete()
                messages.success(request, "Mahsulot sharhi rad etildi.")
            return redirect(f"{reverse('dashboard')}#product-reviews")
        elif action == "update_order_status":
            status = request.POST.get("status")
            if status in dict(Order.STATUS_CHOICES):
                cashback_added = False
                with transaction.atomic():
                    order = get_object_or_404(
                        Order.objects.select_for_update(),
                        pk=request.POST.get("order_id"),
                    )
                    order.status = status
                    if status == "completed" and not order.cashback_credited and order.user_id:
                        cashback = (order.total * CASHBACK_PERCENT / Decimal("100")).quantize(
                            Decimal("1"),
                            rounding=ROUND_HALF_UP,
                        )
                        wallet, _ = Wallet.objects.get_or_create(user_id=order.user_id)
                        Wallet.objects.filter(pk=wallet.pk).update(balance=F("balance") + cashback)
                        order.cashback_amount = cashback
                        order.cashback_credited = True
                        cashback_added = True
                    order.save(update_fields=[
                        "status",
                        "cashback_amount",
                        "cashback_credited",
                    ])
                if cashback_added:
                    messages.success(
                        request,
                        f"#{order.pk} yakunlandi. {order.cashback_amount:,.0f} so‘m keshbek hamyonga qo‘shildi.",
                    )
                else:
                    messages.success(request, f"#{order.pk} buyurtma holati yangilandi.")
            else:
                messages.error(request, "Buyurtma holati noto‘g‘ri tanlandi.")
            return redirect(f"{reverse('dashboard')}#orders")
        elif action in ("approve_topup", "reject_topup"):
            with transaction.atomic():
                topup = get_object_or_404(
                    TopUpRequest.objects.select_for_update().select_related("wallet"),
                    pk=request.POST.get("topup_id"),
                )
                if topup.status != "pending":
                    messages.info(request, "Bu so‘rov avval ko‘rib chiqilgan.")
                else:
                    new_status = "approved" if action == "approve_topup" else "rejected"
                    reviewed_at = timezone.now()
                    updated = TopUpRequest.objects.filter(pk=topup.pk, status="pending").update(
                        status=new_status,
                        reviewed_by=request.user,
                        reviewed_at=reviewed_at,
                    )
                    if updated and new_status == "approved":
                        Wallet.objects.filter(pk=topup.wallet_id).update(balance=F("balance") + topup.amount)
                        messages.success(request, f"{topup.amount:,.0f} so‘m balansga qo‘shildi.")
                    elif updated:
                        messages.info(request, "Balans to‘ldirish so‘rovi rad etildi.")
                    else:
                        messages.info(request, "Bu so‘rov avval ko‘rib chiqilgan.")
            return redirect(f"{reverse('dashboard')}#topups")
        elif action in ("approve_card_change", "reject_card_change"):
            with transaction.atomic():
                card_request = get_object_or_404(
                    CardChangeRequest.objects.select_for_update().select_related("wallet"),
                    pk=request.POST.get("card_request_id"),
                )
                if card_request.status != "pending":
                    messages.info(request, "Bu karta so‘rovi avval ko‘rib chiqilgan.")
                else:
                    new_status = "approved" if action == "approve_card_change" else "rejected"
                    reviewed_at = timezone.now()
                    updated = CardChangeRequest.objects.filter(
                        pk=card_request.pk,
                        status="pending",
                    ).update(status=new_status, reviewed_by=request.user, reviewed_at=reviewed_at)
                    if updated and new_status == "approved":
                        if card_request.action == "add":
                            Wallet.objects.filter(pk=card_request.wallet_id).update(
                                card_last4=card_request.card_last4,
                            )
                            messages.success(request, f"**** {card_request.card_last4} karta tasdiqlandi.")
                        else:
                            Wallet.objects.filter(
                                pk=card_request.wallet_id,
                                card_last4=card_request.card_last4,
                            ).update(card_last4="")
                            messages.success(request, "Karta o‘chirish so‘rovi tasdiqlandi.")
                    elif updated:
                        messages.info(request, "Karta o‘zgartirish so‘rovi rad etildi.")
                    else:
                        messages.info(request, "Bu karta so‘rovi avval ko‘rib chiqilgan.")
            return redirect(f"{reverse('dashboard')}#card-requests")

    today = timezone.localdate()
    first_month_index = today.year * 12 + today.month - 6
    first_year, first_month_index = divmod(first_month_index, 12)
    start_date = date(first_year, first_month_index + 1, 1)
    next_year, next_month_index = divmod(today.year * 12 + today.month, 12)
    end_date = date(next_year, next_month_index + 1, 1)
    start_at = timezone.make_aware(datetime.combine(start_date, time.min))
    end_at = timezone.make_aware(datetime.combine(end_date, time.min))

    monthly_revenue = Order.objects.filter(created_at__gte=start_at, created_at__lt=end_at)
    monthly_revenue = monthly_revenue.exclude(status="cancelled").annotate(
        month=TruncMonth("created_at")
    ).values("month").annotate(revenue=Sum("total"))
    revenue_by_month = {
        (item["month"].year, item["month"].month): item["revenue"]
        for item in monthly_revenue
    }
    month_names = ("Yan", "Fev", "Mar", "Apr", "May", "Iyun", "Iyul", "Avg", "Sen", "Okt", "Noy", "Dek")
    chart_months = []
    for offset in range(5, -1, -1):
        month_index = today.year * 12 + today.month - 1 - offset
        year, month_index = divmod(month_index, 12)
        month = month_index + 1
        chart_months.append({"year": year, "month": month, "label": month_names[month_index]})

    for item in chart_months:
        item["revenue"] = revenue_by_month.get((item["year"], item["month"]), Decimal("0"))
    max_revenue = max((item["revenue"] for item in chart_months), default=Decimal("0"))
    for item in chart_months:
        item["height"] = max(8, round(item["revenue"] / max_revenue * 100)) if max_revenue else 0

    active_orders = Order.objects.exclude(status="cancelled")
    active_order_count = active_orders.count()
    completed_count = active_orders.filter(status="completed").count()
    completion_rate = round(completed_count * 100 / active_order_count) if active_order_count else 0
    revenue_total = active_orders.aggregate(total=Sum("total"))["total"] or Decimal("0")
    product_count = Product.objects.filter(is_approved=True).count()
    products = list(Product.objects.filter(is_approved=True))
    product_rows = [
        {
            "product": product,
            "form": product_form if editing_product_id == product.pk else ProductForm(instance=product),
            "is_editing": editing_product_id == product.pk,
        }
        for product in products
    ]
    pending_ai_products = [
        {
            "product": product,
            "form": product_form if editing_product_id == product.pk else ProductForm(instance=product),
            "is_editing": editing_product_id == product.pk,
        }
        for product in Product.objects.filter(is_ai_generated=True, is_approved=False)
    ]
    category_colors = ("#e6a126", "#3389a7", "#78a94d", "#e27d58", "#7772b8")
    categories = list(
        Product.objects.filter(is_approved=True)
        .values("category")
        .annotate(total=Count("id"))
        .order_by("-total")[:5]
    )
    for index, category in enumerate(categories):
        category["percent"] = round(category["total"] * 100 / product_count) if product_count else 0
        category["color"] = category_colors[index]

    return render(request, "store/dashboard.html", {
        "revenue_total": revenue_total,
        "order_count": Order.objects.count(),
        "pending_count": Order.objects.filter(status__in=("new", "processing")).count(),
        "product_count": product_count,
        "products": product_rows,
        "pending_ai_products": pending_ai_products,
        "pending_ai_count": len(pending_ai_products),
        "pending_reviews": ProductReview.objects.filter(is_approved=False).select_related(
            "product",
            "user",
        )[:20],
        "pending_review_count": ProductReview.objects.filter(is_approved=False).count(),
        "promotions": Promotion.objects.select_related("product").all(),
        "promotion_form": promotion_form,
        "promo_codes": PromoCode.objects.annotate(redemption_count=Count("redemptions")),
        "promo_code_form": promo_code_form,
        "product_form": product_form if editing_product_id is None else ProductForm(),
        "editing_product_id": editing_product_id,
        "chart_months": chart_months,
        "latest_orders": Order.objects.all()[:5],
        "order_status_choices": Order.STATUS_CHOICES,
        "pending_topups": TopUpRequest.objects.filter(status="pending").select_related("wallet__user")[:10],
        "pending_topup_count": TopUpRequest.objects.filter(status="pending").count(),
        "pending_card_requests": CardChangeRequest.objects.filter(status="pending").select_related("wallet__user")[:10],
        "pending_card_request_count": CardChangeRequest.objects.filter(status="pending").count(),
        "categories": categories,
        "category_suggestions": _product_category_choices(),
        "completion_rate": completion_rate,
        "remaining_rate": 100 - completion_rate,
    })


@user_passes_test(_is_admin)
def product_create(request):
    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            product = form.save()
            messages.success(request, f"{product.name} do'konga qo'shildi.")
            return redirect("product_list")
    else:
        form = ProductForm()
    return render(request, "store/product_editor.html", {
        "form": form,
        "is_edit": False,
        "category_suggestions": _product_category_choices(),
    })


@user_passes_test(_is_admin)
def product_update(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, "Mahsulot ma'lumotlari yangilandi.")
            return redirect("product_list")
    else:
        form = ProductForm(instance=product)
    return render(request, "store/product_editor.html", {
        "form": form,
        "is_edit": True,
        "product": product,
        "category_suggestions": _product_category_choices(),
    })


@user_passes_test(_is_admin)
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        name = product.name
        product.delete()
        messages.success(request, f"{name} o'chirildi.")
        return redirect("product_list")
    return render(request, "store/product_confirm_delete.html", {"product": product})


def _cart_summary(saved_cart):
    products = Product.objects.filter(pk__in=saved_cart, is_approved=True)
    items = []
    total = Decimal("0")
    quantity_total = 0

    for product in _apply_marketing_prices(products):
        try:
            quantity = max(1, int(saved_cart[str(product.pk)]))
        except (KeyError, TypeError, ValueError):
            continue
        line_total = product.marketing_price * quantity
        items.append({
            "product": product,
            "quantity": quantity,
            "line_total": line_total,
            "unit_price": product.marketing_price,
            "is_discounted": product.marketing_discounted,
        })
        total += line_total
        quantity_total += quantity

    return items, total, quantity_total


def cart(request):
    items, total, quantity_total = _cart_summary(request.session.get("cart", {}))
    return render(request, "store/cart.html", {"items": items, "total": total, "quantity_total": quantity_total})


def checkout(request):
    saved_cart = request.session.get("cart", {})
    items, total, quantity_total = _cart_summary(saved_cart)
    if not items:
        messages.info(request, "Buyurtma berish uchun avval savatga mahsulot qo‘shing.")
        return redirect("cart")
    if not request.user.is_authenticated:
        messages.info(request, "Balans orqali xarid qilish uchun avval hisobingizga kiring.")
        return redirect(f"{reverse('login')}?next={reverse('checkout')}")

    wallet = Wallet.objects.filter(user=request.user).first()
    if not wallet or not wallet.card_last4:
        messages.warning(request, "Kartangiz qo‘shilmagan. Iltimos, profilingizda karta qo‘shing.")
        return redirect("profile")

    form = CheckoutForm(request.POST or None)
    coupon = None
    discount_amount = Decimal("0")
    total_due = total
    insufficient_balance = False
    if request.method == "POST" and form.is_valid():
        code = form.cleaned_data["coupon_code"].strip().upper()
        if code:
            coupon = PromoCode.objects.filter(code=code).first()
            if coupon is None:
                form.add_error("coupon_code", "Bunday promokod topilmadi.")
            else:
                coupon_error = _coupon_error(coupon, request.user, total, items)
                if coupon_error:
                    form.add_error("coupon_code", coupon_error)
                    coupon = None
                    discount_amount = Decimal("0")
                    total_due = total
                else:
                    discount_amount = _coupon_discount(coupon, total)
                    total_due = total - discount_amount

        if not form.errors:
            with transaction.atomic():
                if coupon:
                    coupon = PromoCode.objects.select_for_update().get(pk=coupon.pk)
                    coupon_error = _coupon_error(coupon, request.user, total, items)
                    if coupon_error:
                        form.add_error("coupon_code", coupon_error)
                if not form.errors:
                    debited = Wallet.objects.filter(pk=wallet.pk, balance__gte=total_due).update(
                        balance=F("balance") - total_due
                    )
                    if not debited:
                        insufficient_balance = True
                    else:
                        order = Order.objects.create(
                            user=request.user,
                            customer_name=form.cleaned_data["customer_name"],
                            phone=form.cleaned_data["phone"],
                            address=form.cleaned_data["address"],
                            total=total_due,
                            subtotal=total,
                            discount_amount=discount_amount,
                            coupon=coupon,
                            coupon_code=coupon.code if coupon else "",
                        )
                        OrderItem.objects.bulk_create(
                            [
                                OrderItem(
                                    order=order,
                                    product=item["product"],
                                    product_name=item["product"].name,
                                    unit_price=item["unit_price"],
                                    quantity=item["quantity"],
                                )
                                for item in items
                            ]
                        )
                        if coupon:
                            CouponRedemption.objects.create(
                                coupon=coupon,
                                user=request.user,
                                order=order,
                            )

            if insufficient_balance:
                wallet.refresh_from_db()
                messages.error(request, "Balansingiz yetarli emas. Iltimos, avval balansingizni to‘ldiring.")
            elif not form.errors:
                request.session["cart"] = {}
                request.session["completed_order_id"] = order.pk
                return redirect("order_complete")

    wallet.refresh_from_db()
    return render(request, "store/checkout.html", {
        "form": form,
        "items": items,
        "total": total_due,
        "subtotal": total,
        "discount_amount": discount_amount,
        "coupon": coupon,
        "quantity_total": quantity_total,
        "wallet": wallet,
        "balance_insufficient": wallet.balance < total_due,
        "insufficient_balance": insufficient_balance,
        "cashback_percent": CASHBACK_PERCENT,
    })


def order_complete(request):
    order_id = request.session.pop("completed_order_id", None)
    if not order_id:
        return redirect("product_list")
    order = get_object_or_404(Order.objects.prefetch_related("items"), pk=order_id)
    return render(request, "store/order_complete.html", {"order": order})


@login_required
def profile(request):
    wallet, _ = Wallet.objects.get_or_create(user=request.user)
    card_form = CardNumberForm()
    topup_form = TopUpForm()
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add_card":
            submitted_form = CardNumberForm(request.POST)
            if submitted_form.is_valid():
                if wallet.card_last4:
                    messages.error(request, "Avval ulangan kartani o‘chirish so‘rovini yuboring.")
                elif wallet.card_change_requests.filter(status="pending").exists():
                    messages.info(request, "Karta bo‘yicha so‘rovingiz admin ko‘rib chiqishini kutmoqda.")
                elif _create_card_change_request(
                    wallet,
                    "add",
                    submitted_form.cleaned_data["card_number"][-4:],
                ):
                    messages.success(request, "Karta qo‘shish so‘rovingiz adminga yuborildi.")
                else:
                    messages.info(request, "Karta bo‘yicha so‘rovingiz admin ko‘rib chiqishini kutmoqda.")
                return redirect(f"{reverse('profile')}#wallet")
            messages.error(request, "Karta raqami 16 ta raqamdan iborat bo‘lishi kerak.")
            return redirect(f"{reverse('profile')}#wallet")
        elif action == "remove_card":
            if wallet.card_last4:
                if wallet.card_change_requests.filter(status="pending").exists():
                    messages.info(request, "Karta bo‘yicha so‘rovingiz admin ko‘rib chiqishini kutmoqda.")
                elif _create_card_change_request(wallet, "remove", wallet.card_last4):
                    messages.success(request, "Karta o‘chirish so‘rovingiz adminga yuborildi.")
                else:
                    messages.info(request, "Karta bo‘yicha so‘rovingiz admin ko‘rib chiqishini kutmoqda.")
            else:
                messages.info(request, "Profilingizda o‘chiriladigan karta yo‘q.")
            return redirect(f"{reverse('profile')}#wallet")
        elif action == "request_topup":
            topup_form = TopUpForm(request.POST)
            if not wallet.card_last4:
                messages.error(request, "Avval karta raqamingizni profilingizga qo‘shing.")
            elif topup_form.is_valid():
                topup = TopUpRequest.objects.create(wallet=wallet, amount=topup_form.cleaned_data["amount"])
                messages.success(request, f"{topup.amount:,.0f} so‘m uchun so‘rov adminga yuborildi.")
                return redirect(f"{reverse('profile')}#wallet")

    orders = Order.objects.filter(user=request.user).prefetch_related("items", "items__product")
    return render(request, "store/profile.html", {
        "orders": orders,
        "order_count": orders.count(),
        "wallet": wallet,
        "card_form": card_form,
        "topup_form": topup_form,
        "topup_requests": wallet.top_up_requests.all()[:8],
        "card_change_requests": wallet.card_change_requests.all()[:8],
        "has_pending_card_change": wallet.card_change_requests.filter(status="pending").exists(),
    })


@login_required
@require_GET
def topup_status(request):
    wallet = Wallet.objects.filter(user=request.user).first()
    requests = wallet.top_up_requests.all()[:8] if wallet else []
    card_requests = wallet.card_change_requests.all()[:8] if wallet else []
    orders = Order.objects.filter(user=request.user).order_by("-created_at")
    return JsonResponse({
        "balance": str(wallet.balance) if wallet else "0",
        "requests": [
            {
                "id": topup.pk,
                "status": topup.status,
                "label": topup.get_status_display(),
                "amount": str(topup.amount),
            }
            for topup in requests
        ],
        "card_requests": [
            {
                "id": card_request.pk,
                "action": card_request.action,
                "action_label": card_request.get_action_display(),
                "status": card_request.status,
                "label": card_request.get_status_display(),
                "card_last4": card_request.card_last4,
            }
            for card_request in card_requests
        ],
        "orders": [
            {
                "id": order.pk,
                "status": order.status,
                "label": order.get_status_display(),
            }
            for order in orders
        ],
    })


@require_POST
def cart_update(request, pk):
    product = get_object_or_404(Product, pk=pk, is_approved=True)
    saved_cart = request.session.get("cart", {})
    try:
        quantity = max(0, int(saved_cart.get(str(product.pk), 0)))
    except (TypeError, ValueError):
        quantity = 0

    action = request.POST.get("action")
    if action == "remove":
        saved_cart.pop(str(product.pk), None)
        request.session["cart"] = saved_cart
        messages.success(request, f"{product.name} savatdan olib tashlandi.")
        return redirect("cart")

    if action == "add":
        quantity += 1
    elif action == "increase":
        quantity = max(1, quantity) + 1
    elif action == "decrease":
        if quantity > 1:
            quantity -= 1
        elif quantity == 0:
            return redirect("cart")
    else:
        return redirect("cart")

    saved_cart[str(product.pk)] = quantity
    request.session["cart"] = saved_cart
    return redirect("cart")