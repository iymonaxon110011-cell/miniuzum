from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth.models import User
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from allauth.socialaccount.adapter import get_adapter
from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount, SocialApp, SocialLogin
from PIL import Image
from django.utils import timezone

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
from .services import generate_daily_product_suggestion


class ProductStoreTests(TestCase):
    def setUp(self):
        self.product = Product.objects.create(
            name="Sinov quloqchin",
            category="Elektronika",
            description="Yengil va qulay",
            price=250000,
            old_price=300000,
        )

    @override_settings(DEBUG=False)
    def test_unknown_url_renders_branded_not_found_page(self):
        response = self.client.get("/this-page-does-not-exist/")

        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Voy, bu sahifa", status_code=404)
        self.assertContains(response, "XATO KODI · 404", status_code=404)
        self.assertContains(response, reverse("product_list"), status_code=404)

    @override_settings(DEBUG=False)
    def test_uploaded_media_is_served_when_debug_is_disabled(self):
        with TemporaryDirectory(dir=settings.MEDIA_ROOT) as media_root:
            media_file = Path(media_root) / "test-image.jpg"
            media_file.write_bytes(b"test image content")
            media_path = f"/media/{Path(media_root).name}/test-image.jpg"
            response = self.client.get(media_path)
            content = b"".join(response.streaming_content) if response.streaming else response.content
            response.close()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(content, b"test image content")

    def test_google_login_button_uses_admin_social_application_on_login_and_register(self):
        SocialApp.objects.create(
            provider="google",
            name="Google",
            client_id="test-client-id",
            secret="test-client-secret",
        )

        for url_name in ("login", "register"):
            response = self.client.get(reverse(url_name))

            self.assertEqual(response.status_code, 200)
            self.assertIn("google", [provider.id for provider in get_adapter().list_providers(response.wsgi_request)])
            self.assertContains(response, "Google bilan davom etish")
            self.assertContains(response, "/accounts/google/login/")

    def test_login_and_register_work_without_google_social_application(self):
        for url_name in ("login", "register"):
            response = self.client.get(reverse(url_name))

            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, "Google bilan davom etish")

    def test_google_verified_email_logs_into_matching_local_account(self):
        SocialApp.objects.create(
            provider="google",
            name="Google",
            client_id="test-client-id",
            secret="test-client-secret",
        )
        user = User.objects.create_user(
            username="google-user",
            email="existing@example.com",
            password="test-password",
        )
        provider = get_adapter().get_provider(RequestFactory().get("/"), "google")
        social_login = SocialLogin(
            user=User(username="google-user", email="existing@example.com"),
            account=SocialAccount(provider="google", uid="google-user-id"),
            email_addresses=[EmailAddress(email="existing@example.com", verified=True)],
            provider=provider,
        )

        social_login.lookup()

        self.assertEqual(social_login.user, user)
        self.assertEqual(social_login._did_authenticate_by_email, user.email)
        self.assertTrue(get_adapter().can_authenticate_by_email(social_login, user.email))

    def login_as_admin(self):
        admin = User.objects.create_user(username="admin", password="Uzum-test-pass-482!", is_staff=True)
        self.client.force_login(admin)

    def test_dashboard_shows_live_store_metrics_for_staff(self):
        self.login_as_admin()
        Order.objects.create(
            customer_name="Ali Valiyev",
            phone="+998901234567",
            address="Toshkent",
            total=500000,
            status="completed",
        )
        Order.objects.create(
            customer_name="Madina Karimova",
            phone="+998901112233",
            address="Samarqand",
            total=250000,
            status="new",
        )

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["revenue_total"], 750000)
        self.assertEqual(response.context["order_count"], 2)
        self.assertEqual(response.context["pending_count"], 1)
        self.assertEqual(response.context["product_count"], Product.objects.filter(is_approved=True).count())
        self.assertContains(response, "Madina Karimova")
        self.assertContains(response, "Boshqaruv paneli")
        self.assertNotContains(response, "Dashboard — Uzum Market")

    def test_daily_product_suggestion_is_created_once_and_hidden_until_approved(self):
        today = timezone.localdate()
        suggestion = generate_daily_product_suggestion(today)

        self.assertIsNotNone(suggestion)
        self.assertFalse(suggestion.is_approved)
        self.assertTrue(suggestion.is_ai_generated)
        self.assertIsNone(generate_daily_product_suggestion(today))

        catalog = self.client.get(reverse("product_list"))
        self.assertNotContains(catalog, suggestion.name)
        self.assertEqual(
            self.client.get(reverse("product_detail", args=[suggestion.pk])).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                reverse("cart_update", args=[suggestion.pk]),
                {"action": "add"},
            ).status_code,
            404,
        )

        self.login_as_admin()
        dashboard = self.client.get(reverse("dashboard"))
        self.assertContains(dashboard, suggestion.name)
        self.assertContains(dashboard, "API kalitisiz yaratilgan demo takliflar")

        response = self.client.post(
            reverse("dashboard"),
            {"action": "approve_ai_product", "product_id": suggestion.pk},
        )
        self.assertRedirects(response, f"{reverse('dashboard')}#ai-products")
        suggestion.refresh_from_db()
        self.assertTrue(suggestion.is_approved)
        self.assertContains(self.client.get(reverse("product_list")), suggestion.name)

    def test_dashboard_can_reject_daily_product_suggestion(self):
        suggestion = generate_daily_product_suggestion(timezone.localdate() + timedelta(days=1))
        self.login_as_admin()

        response = self.client.post(
            reverse("dashboard"),
            {"action": "reject_ai_product", "product_id": suggestion.pk},
        )

        self.assertRedirects(response, f"{reverse('dashboard')}#ai-products")
        self.assertFalse(Product.objects.filter(pk=suggestion.pk).exists())

    def test_dashboard_redirects_non_staff_users(self):
        response = self.client.get(reverse("dashboard"))

        self.assertRedirects(response, f"{reverse('login')}?next={reverse('dashboard')}")

    def test_dashboard_can_create_product_without_leaving_dashboard(self):
        self.login_as_admin()

        response = self.client.post(
            reverse("dashboard"),
            {
                "action": "save_product",
                "name": "Dashboard mahsuloti",
                "category": "Elektronika",
                "price": "180000",
                "old_price": "220000",
                "description": "Dashboarddan qo‘shildi",
            },
        )

        self.assertRedirects(response, f"{reverse('dashboard')}#products")
        product = Product.objects.get(name="Dashboard mahsuloti")
        self.assertTrue(product.is_approved)
        self.assertFalse(product.is_ai_generated)

    def test_dashboard_can_create_promotion_and_homepage_displays_it(self):
        self.login_as_admin()
        with TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                image_buffer = BytesIO()
                Image.new("RGB", (24, 24), "green").save(image_buffer, format="PNG")
                upload = SimpleUploadedFile("aksiya.png", image_buffer.getvalue(), content_type="image/png")
                response = self.client.post(
                    reverse("dashboard"),
                    {
                        "action": "save_promotion",
                        "title": "Yozgi chegirma",
                        "subtitle": "Tanlangan mahsulotlarga chegirma",
                        "category": "Elektronika",
                        "discount_label": "−25%",
                        "is_active": "on",
                        "image": upload,
                    },
                )

                self.assertRedirects(response, f"{reverse('dashboard')}#promotions")
                promotion = Promotion.objects.get(title="Yozgi chegirma")
                self.assertTrue(promotion.image_url.startswith("/media/promotions/"))
                relative_path = promotion.image_url.removeprefix("/media/")
                self.assertTrue((Path(media_root) / relative_path).is_file())
                dashboard = self.client.get(reverse("dashboard"))
                self.assertContains(dashboard, "Aksiya qo‘shish")
                self.assertContains(dashboard, "Yozgi chegirma")
                homepage = self.client.get(reverse("product_list"))
                self.assertContains(homepage, "Yozgi chegirma")
                self.assertNotContains(homepage, "Sevimli texnikangiz")

    def test_dashboard_can_target_promotion_to_a_product(self):
        self.login_as_admin()
        with TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                image_buffer = BytesIO()
                Image.new("RGB", (24, 24), "green").save(image_buffer, format="PNG")
                upload = SimpleUploadedFile("mahsulot-aksiya.png", image_buffer.getvalue(), content_type="image/png")
                response = self.client.post(
                    reverse("dashboard"),
                    {
                        "action": "save_promotion",
                        "title": "Quloqchin aksiyasi",
                        "subtitle": "Faqat ushbu mahsulot uchun",
                        "product": self.product.pk,
                        "discount_label": "−15%",
                        "is_active": "on",
                        "image": upload,
                    },
                )

                self.assertRedirects(response, f"{reverse('dashboard')}#promotions")
                promotion = Promotion.objects.get(title="Quloqchin aksiyasi")
                self.assertEqual(promotion.product, self.product)
                self.assertEqual(promotion.category, "")

                dashboard = self.client.get(reverse("dashboard"))
                self.assertContains(dashboard, f"Mahsulot: {self.product.name}")
                homepage = self.client.get(reverse("product_list"))
                self.assertContains(homepage, f'href="{reverse("product_detail", args=[self.product.pk])}"')
                self.assertContains(homepage, "Quloqchin aksiyasi")

    def test_dashboard_can_create_and_pause_a_promo_code(self):
        self.login_as_admin()
        response = self.client.post(
            reverse("dashboard"),
            {
                "action": "save_promo_code",
                "code": "welcome10",
                "discount_type": "percent",
                "discount_value": "10",
                "minimum_order": "50000",
                "max_uses": "20",
                "is_active": "on",
            },
        )

        self.assertRedirects(response, f"{reverse('dashboard')}#promo-codes")
        promo_code = PromoCode.objects.get(code="WELCOME10")
        self.assertEqual(promo_code.max_uses, 20)
        self.assertContains(self.client.get(reverse("dashboard")), "WELCOME10")

        response = self.client.post(
            reverse("dashboard"),
            {"action": "toggle_promo_code", "promo_code_id": promo_code.pk},
        )
        self.assertRedirects(response, f"{reverse('dashboard')}#promo-codes")
        promo_code.refresh_from_db()
        self.assertFalse(promo_code.is_active)

    def test_dashboard_can_edit_product_without_leaving_dashboard(self):
        self.login_as_admin()

        response = self.client.post(
            reverse("dashboard"),
            {
                "action": "save_product",
                "product_id": self.product.pk,
                "name": "Yangilangan quloqchin",
                "category": "Elektronika",
                "price": "210000",
                "old_price": "260000",
                "description": "Dashboard ichida tahrirlandi",
            },
        )

        self.assertRedirects(response, f"{reverse('dashboard')}#products")
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, "Yangilangan quloqchin")
        self.assertEqual(self.product.price, 210000)

    def test_dashboard_can_delete_product_without_leaving_dashboard(self):
        self.login_as_admin()

        response = self.client.post(
            reverse("dashboard"),
            {"action": "delete_product", "product_id": self.product.pk},
        )

        self.assertRedirects(response, f"{reverse('dashboard')}#products")
        self.assertFalse(Product.objects.filter(pk=self.product.pk).exists())

    def test_dashboard_can_update_order_status_without_leaving_dashboard(self):
        self.login_as_admin()
        order = Order.objects.create(
            customer_name="Ali Valiyev",
            phone="+998901234567",
            address="Toshkent",
            total=250000,
        )

        response = self.client.post(
            reverse("dashboard"),
            {"action": "update_order_status", "order_id": order.pk, "status": "processing"},
        )

        self.assertRedirects(response, f"{reverse('dashboard')}#orders")
        order.refresh_from_db()
        self.assertEqual(order.status, "processing")

    def test_profile_shows_purchases_and_admin_updated_status(self):
        customer = User.objects.create_user(username="customer", password="Uzum-customer-pass-482!")
        admin = User.objects.create_user(username="admin", password="Uzum-admin-pass-482!", is_staff=True)
        order = Order.objects.create(
            user=customer,
            customer_name="Customer User",
            phone="+998901234567",
            address="Toshkent",
            total=500000,
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            product_name="Sinov quloqchin",
            unit_price=250000,
            quantity=2,
        )
        other_order = Order.objects.create(
            customer_name="Boshqa mijoz",
            phone="+998901112233",
            address="Samarqand",
            total=100000,
        )
        OrderItem.objects.create(
            order=other_order,
            product_name="Boshqa xarid",
            unit_price=100000,
            quantity=1,
        )

        self.client.force_login(admin)
        self.client.post(
            reverse("dashboard"),
            {"action": "update_order_status", "order_id": order.pk, "status": "processing"},
        )
        self.client.force_login(customer)
        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sinov quloqchin")
        self.assertContains(response, "Jarayonda")
        self.assertNotContains(response, "Boshqa xarid")

    def test_profile_requires_login(self):
        response = self.client.get(reverse("profile"))

        self.assertRedirects(response, f"{reverse('login')}?next={reverse('profile')}")

    def test_profile_card_add_waits_for_admin_approval_and_stores_only_last_four(self):
        customer = User.objects.create_user(username="carduser", password="Uzum-card-pass-482!")
        self.client.force_login(customer)

        invalid_response = self.client.post(reverse("profile"), {"action": "add_card", "card_number": "123456789012345"})

        self.assertRedirects(invalid_response, f"{reverse('profile')}#wallet")
        wallet = Wallet.objects.get(user=customer)
        self.assertEqual(wallet.card_last4, "")

        response = self.client.post(reverse("profile"), {"action": "add_card", "card_number": "1234567812345678"})

        self.assertRedirects(response, f"{reverse('profile')}#wallet")
        card_request = CardChangeRequest.objects.get(wallet=wallet)
        self.assertEqual(card_request.action, "add")
        self.assertEqual(card_request.card_last4, "5678")
        self.assertEqual(card_request.status, "pending")
        wallet.refresh_from_db()
        self.assertEqual(wallet.card_last4, "")

        self.login_as_admin()
        self.client.post(reverse("dashboard"), {
            "action": "approve_card_change",
            "card_request_id": card_request.pk,
        })

        wallet.refresh_from_db()
        card_request.refresh_from_db()
        self.assertEqual(wallet.card_last4, "5678")
        self.assertEqual(card_request.status, "approved")
        self.client.force_login(customer)
        status_response = self.client.get(reverse("topup_status"))
        self.assertEqual(status_response.json()["card_requests"][0]["status"], "approved")

    def test_profile_card_removal_waits_for_admin_approval_without_changing_balance(self):
        customer = User.objects.create_user(username="carduser", password="Uzum-card-pass-482!")
        wallet = Wallet.objects.create(user=customer, card_last4="5678", balance=25000)
        self.client.force_login(customer)

        response = self.client.post(reverse("profile"), {"action": "remove_card"})

        self.assertRedirects(response, f"{reverse('profile')}#wallet")
        card_request = CardChangeRequest.objects.get(wallet=wallet)
        self.assertEqual(card_request.action, "remove")
        self.assertEqual(card_request.status, "pending")
        wallet.refresh_from_db()
        self.assertEqual(wallet.card_last4, "5678")

        self.login_as_admin()
        self.client.post(reverse("dashboard"), {
            "action": "approve_card_change",
            "card_request_id": card_request.pk,
        })

        wallet.refresh_from_db()
        card_request.refresh_from_db()
        self.assertEqual(wallet.card_last4, "")
        self.assertEqual(wallet.balance, 25000)
        self.assertEqual(card_request.status, "approved")

    def test_admin_rejecting_card_request_leaves_wallet_unchanged(self):
        customer = User.objects.create_user(username="rejectcard")
        wallet = Wallet.objects.create(user=customer)
        card_request = CardChangeRequest.objects.create(wallet=wallet, action="add", card_last4="5678")
        self.login_as_admin()

        response = self.client.post(reverse("dashboard"), {
            "action": "reject_card_change",
            "card_request_id": card_request.pk,
        })

        self.assertRedirects(response, f"{reverse('dashboard')}#card-requests")
        wallet.refresh_from_db()
        card_request.refresh_from_db()
        self.assertEqual(wallet.card_last4, "")
        self.assertEqual(card_request.status, "rejected")

    def test_topup_waits_for_admin_and_approval_credits_once(self):
        customer = User.objects.create_user(username="walletuser", password="Uzum-wallet-pass-482!")
        wallet = Wallet.objects.create(user=customer, card_last4="4321")
        self.client.force_login(customer)

        response = self.client.post(reverse("profile"), {"action": "request_topup", "amount": "125000"})

        self.assertRedirects(response, f"{reverse('profile')}#wallet")
        topup = TopUpRequest.objects.get(wallet=wallet)
        self.assertEqual(topup.status, "pending")
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, 0)

        self.login_as_admin()
        approve_data = {"action": "approve_topup", "topup_id": topup.pk}
        self.assertRedirects(
            self.client.post(reverse("dashboard"), approve_data),
            f"{reverse('dashboard')}#topups",
        )
        self.client.post(reverse("dashboard"), approve_data)

        wallet.refresh_from_db()
        topup.refresh_from_db()
        self.assertEqual(wallet.balance, 125000)
        self.assertEqual(topup.status, "approved")

    def test_topup_status_only_exposes_logged_in_users_requests(self):
        customer = User.objects.create_user(username="walletuser", password="Uzum-wallet-pass-482!")
        other_customer = User.objects.create_user(username="otherwallet", password="Uzum-wallet-pass-482!")
        wallet = Wallet.objects.create(user=customer, balance=25000)
        other_wallet = Wallet.objects.create(user=other_customer)
        own_topup = TopUpRequest.objects.create(wallet=wallet, amount=125000)
        TopUpRequest.objects.create(wallet=other_wallet, amount=999000)
        own_card_request = CardChangeRequest.objects.create(wallet=wallet, action="add", card_last4="5678")
        CardChangeRequest.objects.create(wallet=other_wallet, action="add", card_last4="9876")
        own_order = Order.objects.create(
            user=customer,
            customer_name="Wallet User",
            phone="+998901234567",
            address="Toshkent",
            total=50000,
            status="processing",
        )
        Order.objects.create(
            user=other_customer,
            customer_name="Other User",
            phone="+998901112233",
            address="Samarqand",
            total=75000,
        )
        self.client.force_login(customer)

        response = self.client.get(reverse("topup_status"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "balance": "25000",
            "requests": [{
                "id": own_topup.pk,
                "status": "pending",
                "label": "Ko‘rib chiqilmoqda",
                "amount": "125000",
            }],
            "card_requests": [{
                "id": own_card_request.pk,
                "action": "add",
                "action_label": "Karta qo‘shish",
                "status": "pending",
                "label": "Ko‘rib chiqilmoqda",
                "card_last4": "5678",
            }],
            "orders": [{
                "id": own_order.pk,
                "status": "processing",
                "label": "Jarayonda",
            }],
        })

    def test_checkout_blocks_guest_and_missing_card(self):
        self.client.post(reverse("cart_update", args=[self.product.pk]), {"action": "add"})
        response = self.client.get(reverse("checkout"))

        self.assertRedirects(response, f"{reverse('login')}?next={reverse('checkout')}")

        customer = User.objects.create_user(username="buyer", password="Uzum-buyer-pass-482!")
        self.client.force_login(customer)
        response = self.client.get(reverse("checkout"))

        self.assertRedirects(response, reverse("profile"))
        self.assertTrue(any("Kartangiz qo‘shilmagan" in str(message) for message in response.wsgi_request._messages))

    def test_checkout_rejects_insufficient_wallet_balance(self):
        customer = User.objects.create_user(username="lowbalance", password="Uzum-low-pass-482!")
        Wallet.objects.create(user=customer, card_last4="4321", balance=100000)
        self.client.force_login(customer)
        self.client.post(reverse("cart_update", args=[self.product.pk]), {"action": "add"})

        response = self.client.post(
            reverse("checkout"),
            {"customer_name": "Ali Valiyev", "phone": "+998901234567", "address": "Toshkent"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["insufficient_balance"])
        self.assertContains(response, "Balansingiz yetarli emas")
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(self.client.session["cart"], {str(self.product.pk): 1})

    def test_catalog_shows_products_and_add_link(self):
        response = self.client.get(reverse("product_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.product.name)
        self.assertContains(response, reverse("product_detail", args=[self.product.pk]))
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertNotContains(response, reverse("product_update", args=[self.product.pk]))
        self.assertNotContains(response, reverse("product_create"))

    def test_product_photo_opens_full_detail_page(self):
        response = self.client.get(reverse("product_detail", args=[self.product.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.product.name)
        self.assertContains(response, self.product.description)
        self.assertContains(response, "Namuna sharhlar")
        self.assertContains(response, "Sahifa ko‘rinishi uchun namunalar")
        self.assertContains(response, "250000")
        self.assertContains(response, "300000")
        self.assertNotContains(response, reverse("product_update", args=[self.product.pk]))

    def test_only_completed_buyers_can_submit_reviews_and_admin_must_approve(self):
        detail_url = reverse("product_detail", args=[self.product.pk])
        guest_response = self.client.post(
            detail_url,
            {"rating": "5", "comment": "Zo‘r mahsulot"},
        )
        self.assertRedirects(guest_response, f"{reverse('login')}?next={detail_url}%23reviews")
        self.assertFalse(ProductReview.objects.exists())

        buyer = User.objects.create_user(username="verified-buyer", password="pass")
        self.client.force_login(buyer)
        self.client.post(detail_url, {"rating": "5", "comment": "Zo‘r mahsulot"})
        self.assertFalse(ProductReview.objects.exists())

        order = Order.objects.create(
            user=buyer,
            customer_name="Verified Buyer",
            phone="+998901234567",
            address="Toshkent",
            total=self.product.price,
            status="processing",
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            product_name=self.product.name,
            unit_price=self.product.price,
            quantity=1,
        )
        self.client.post(detail_url, {"rating": "5", "comment": "Zo‘r mahsulot"})
        self.assertFalse(ProductReview.objects.exists())

        order.status = "completed"
        order.save(update_fields=["status"])
        response = self.client.post(
            detail_url,
            {"rating": "5", "comment": "Haqiqiy xaridimdan mamnunman"},
        )
        self.assertRedirects(response, f"{detail_url}#reviews")
        review = ProductReview.objects.get()
        self.assertFalse(review.is_approved)

        pending_page = self.client.get(detail_url)
        self.assertContains(pending_page, "Sharhingiz admin tekshiruvini kutmoqda.")
        self.assertNotContains(pending_page, "Haqiqiy xaridimdan mamnunman")

        self.login_as_admin()
        self.assertContains(self.client.get(reverse("dashboard")), "Haqiqiy xaridimdan mamnunman")
        approval_response = self.client.post(
            reverse("dashboard"),
            {"action": "approve_review", "review_id": review.pk},
        )
        self.assertRedirects(approval_response, f"{reverse('dashboard')}#product-reviews")
        review.refresh_from_db()
        self.assertTrue(review.is_approved)

        public_page = self.client.get(detail_url)
        self.assertContains(public_page, "Haqiqiy xaridimdan mamnunman")
        self.assertContains(public_page, "Xaridi tasdiqlangan")
        self.assertNotContains(public_page, "Namuna sharhlar")
        self.assertContains(public_page, "5,0")

        self.client.force_login(buyer)
        self.client.post(detail_url, {"rating": "4", "comment": "Ikkinchi sharh"})
        self.assertEqual(ProductReview.objects.filter(product=self.product, user=buyer).count(), 1)

    def test_admin_can_reject_product_review(self):
        buyer = User.objects.create_user(username="review-buyer", password="pass")
        order = Order.objects.create(
            user=buyer,
            customer_name="Review Buyer",
            phone="+998901234567",
            address="Toshkent",
            total=self.product.price,
            status="completed",
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            product_name=self.product.name,
            unit_price=self.product.price,
            quantity=1,
        )
        self.client.force_login(buyer)
        self.client.post(
            reverse("product_detail", args=[self.product.pk]),
            {"rating": "2", "comment": "Tekshiruv uchun"},
        )
        review = ProductReview.objects.get()

        self.login_as_admin()
        response = self.client.post(
            reverse("dashboard"),
            {"action": "reject_review", "review_id": review.pk},
        )

        self.assertRedirects(response, f"{reverse('dashboard')}#product-reviews")
        self.assertFalse(ProductReview.objects.filter(pk=review.pk).exists())

    def test_add_form_uses_image_picker_and_preview(self):
        self.login_as_admin()
        response = self.client.get(reverse("product_create"))

        self.assertContains(response, 'enctype="multipart/form-data"')
        self.assertContains(response, 'id="id_image"')
        self.assertContains(response, "data-image-preview")
        self.assertContains(response, "Rasmni tanlash")
        self.assertNotContains(response, 'id="id_image_url"')

    def test_admin_can_create_product_with_custom_category_and_catalog_lists_it(self):
        self.login_as_admin()

        response = self.client.post(
            reverse("product_create"),
            {
                "name": "Mushuk uchun o‘yinchoq",
                "category": "  Uy hayvonlari  ",
                "price": "45000",
                "old_price": "",
                "description": "Yangi turkum mahsuloti",
            },
        )

        self.assertRedirects(response, reverse("product_list"))
        product = Product.objects.get(name="Mushuk uchun o‘yinchoq")
        self.assertEqual(product.category, "Uy hayvonlari")

        catalog = self.client.get(reverse("product_list"))
        self.assertContains(catalog, "Uy hayvonlari")
        self.assertContains(catalog, "?category=Uy%20hayvonlari")

    def test_product_category_field_allows_manual_entry_and_suggests_existing_categories(self):
        self.login_as_admin()
        Product.objects.create(name="Turkum namunasi", category="Uy hayvonlari", price=10000)

        response = self.client.get(reverse("product_create"))

        self.assertContains(response, 'list="product-category-options"')
        self.assertContains(response, '<option value="Uy hayvonlari">')

    def test_search_and_category_filter(self):
        response = self.client.get(reverse("product_list"), {"q": "quloqchin", "category": "Elektronika"})

        self.assertContains(response, self.product.name)

    def test_search_corrects_a_typo_when_matching_products_exist(self):
        product = Product.objects.create(
            name="iPhone 15 Pro",
            category="Elektronika",
            price=12000000,
        )

        response = self.client.get(reverse("product_list"), {"q": "ipone 15 pro"})

        self.assertEqual(list(response.context["products"]), [product])
        self.assertEqual(response.context["search_corrected_query"], "iphone 15 pro")
        self.assertContains(response, "ipone 15 pro")
        self.assertContains(response, "iphone 15 pro")
        self.assertContains(response, 'list="product-search-suggestions"')
        self.assertContains(response, '<option value="iPhone 15 Pro">')

    def test_search_keeps_exact_results_without_offering_a_correction(self):
        response = self.client.get(reverse("product_list"), {"q": "quloqchin"})

        self.assertContains(response, self.product.name)
        self.assertEqual(response.context["search_corrected_query"], "")

    def test_catalog_filters_by_brand_and_sorts_by_price(self):
        cheaper = Product.objects.create(name="Arzon mahsulot", brand="Acme", price=100000)
        other_brand = Product.objects.create(name="Boshqa mahsulot", brand="Other", price=50000)

        response = self.client.get(reverse("product_list"), {"brand": "Ac", "sort": "price_asc"})

        self.assertEqual(list(response.context["products"]), [cheaper])
        self.assertContains(response, "Acme")
        self.assertNotContains(response, other_brand.name)

        response = self.client.get(reverse("product_list"), {"sort": "price_desc"})
        prices = list(response.context["products"].values_list("price", flat=True))
        self.assertEqual(prices, sorted(prices, reverse=True))

    def test_catalog_filters_by_price_range(self):
        matching = Product.objects.create(name="Oraliqdagi mahsulot", price=999999999997)
        outside = Product.objects.create(name="Oraliqdan tashqaridagi mahsulot", price=999999999999)

        response = self.client.get(
            reverse("product_list"),
            {"min_price": "999999999997", "max_price": "999999999998"},
        )

        self.assertEqual(list(response.context["products"]), [matching])
        self.assertEqual(response.context["selected_min_price"], Decimal("999999999997"))
        self.assertEqual(response.context["selected_max_price"], Decimal("999999999998"))
        self.assertEqual(response.context["price_range_max"], outside.price)
        self.assertContains(response, "Narx, baho, so‘m")
        self.assertNotContains(response, outside.name)

    def test_catalog_rejects_invalid_price_range_without_failing(self):
        response = self.client.get(
            reverse("product_list"),
            {"min_price": "not-a-price", "max_price": "1000000000000"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertCountEqual(
            list(response.context["products"]),
            Product.objects.filter(is_approved=True),
        )
        self.assertEqual(response.context["selected_min_price"], None)
        self.assertEqual(response.context["selected_max_price"], None)
        self.assertContains(response, "Narxni to‘g‘ri kiriting.")
        self.assertContains(response, "Narx 999 999 999 999 so‘mdan oshmasligi kerak.")

    def test_catalog_filters_by_multiple_colors_and_seasons(self):
        matching = Product.objects.create(
            name="Bahorgi qizil ko‘ylak",
            category="Kiyim",
            color="red",
            season="spring",
            price=100000,
        )
        matching_blue = Product.objects.create(
            name="Bahorgi ko‘k kiyim",
            category="Kiyim",
            color="blue",
            season="spring",
            price=130000,
        )
        Product.objects.create(name="Qishki qizil kiyim", category="Kiyim", color="red", season="winter", price=120000)

        response = self.client.get(
            reverse("product_list"),
            {"category": "Kiyim", "color": ["red", "blue"], "season": ["spring"]},
        )

        self.assertCountEqual(list(response.context["products"]), [matching, matching_blue])
        self.assertEqual(response.context["selected_colors"], ["red", "blue"])
        self.assertEqual(response.context["selected_seasons"], ["spring"])
        self.assertContains(response, "catalog-filter-group--season")

    def test_season_filter_is_ignored_and_hidden_for_non_clothing_categories(self):
        electronics = Product.objects.create(
            name="Qishki elektronika",
            category="Elektronika",
            season="winter",
            price=100000,
        )

        response = self.client.get(
            reverse("product_list"),
            {"category": "Elektronika", "season": "spring"},
        )

        self.assertIn(electronics, response.context["products"])
        self.assertEqual(response.context["selected_seasons"], [])
        self.assertNotContains(response, "catalog-filter-group--season")

    def test_wishlist_requires_login_and_can_add_and_remove_products(self):
        wishlist_url = reverse("wishlist")
        toggle_url = reverse("wishlist_toggle", args=[self.product.pk])

        response = self.client.get(wishlist_url)
        self.assertRedirects(response, f"{reverse('login')}?next={wishlist_url}")

        customer = User.objects.create_user(username="wishlist-customer", password="safe-password")
        self.client.force_login(customer)
        response = self.client.post(toggle_url, {"next": wishlist_url})
        self.assertRedirects(response, wishlist_url)
        self.assertTrue(WishlistItem.objects.filter(user=customer, product=self.product).exists())
        self.assertContains(self.client.get(wishlist_url), self.product.name)

        self.client.post(toggle_url, {"next": wishlist_url})
        self.assertFalse(WishlistItem.objects.filter(user=customer, product=self.product).exists())

    def test_wishlist_toggle_rejects_external_redirect(self):
        customer = User.objects.create_user(username="wishlist-customer", password="safe-password")
        self.client.force_login(customer)

        response = self.client.post(reverse("wishlist_toggle", args=[self.product.pk]), {"next": "https://example.com"})

        self.assertRedirects(response, reverse("wishlist"))

    def test_product_cannot_be_created_without_admin(self):
        response = self.client.post(
            reverse("product_create"),
            {
                "name": "Yangi karnay",
                "category": "Elektronika",
                "price": "180000",
                "old_price": "220000",
                "description": "Ixcham ovoz kuchaytirgich",
                "image_url": "",
            },
        )

        self.assertRedirects(response, f"{reverse('login')}?next={reverse('product_create')}")
        self.assertFalse(Product.objects.filter(name="Yangi karnay", price=180000).exists())

    def test_admin_can_create_product(self):
        self.login_as_admin()
        response = self.client.post(
            reverse("product_create"),
            {"name": "Yangi karnay", "category": "Elektronika", "price": "180000", "old_price": "", "description": "", "image_url": ""},
        )

        self.assertRedirects(response, reverse("product_list"))
        self.assertTrue(Product.objects.filter(name="Yangi karnay", price=180000).exists())

    def test_product_image_can_be_uploaded_as_a_file(self):
        self.login_as_admin()
        with TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                image_buffer = BytesIO()
                Image.new("RGB", (24, 24), "purple").save(image_buffer, format="PNG")
                upload = SimpleUploadedFile("yangi-rasm.png", image_buffer.getvalue(), content_type="image/png")
                response = self.client.post(
                    reverse("product_create"),
                    {
                        "name": "Rasmli mahsulot",
                        "category": "Elektronika",
                        "price": "120000",
                        "old_price": "",
                        "description": "Rasm yuklash sinovi",
                        "image": upload,
                    },
                )

                self.assertRedirects(response, reverse("product_list"))
                product = Product.objects.get(name="Rasmli mahsulot")
                self.assertTrue(product.image_url.startswith("/media/products/"))
                relative_path = product.image_url.removeprefix("/media/")
                self.assertTrue((Path(media_root) / relative_path).is_file())

    def test_product_price_can_be_updated(self):
        self.login_as_admin()
        response = self.client.post(
            reverse("product_update", args=[self.product.pk]),
            {
                "name": self.product.name,
                "category": self.product.category,
                "price": "200000",
                "old_price": "300000",
                "description": self.product.description,
                "image_url": "",
            },
        )

        self.assertRedirects(response, reverse("product_list"))
        self.product.refresh_from_db()
        self.assertEqual(self.product.price, 200000)

    def test_product_is_deleted_after_confirmation(self):
        self.login_as_admin()
        response = self.client.get(reverse("product_delete", args=[self.product.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())

        response = self.client.post(reverse("product_delete", args=[self.product.pk]))

        self.assertRedirects(response, reverse("product_list"))
        self.assertFalse(Product.objects.filter(pk=self.product.pk).exists())

    def test_cart_add_quantity_and_total(self):
        update_url = reverse("cart_update", args=[self.product.pk])
        self.client.post(update_url, {"action": "add"})
        self.client.post(update_url, {"action": "increase"})

        response = self.client.get(reverse("cart"))

        self.assertContains(response, "500000")
        self.assertEqual(response.context["items"][0]["quantity"], 2)
        self.assertEqual(response.context["total"], 500000)
        self.assertEqual(response.context["quantity_total"], 2)

    def test_cart_decrease_does_not_go_below_one(self):
        update_url = reverse("cart_update", args=[self.product.pk])
        self.client.post(update_url, {"action": "add"})
        self.client.post(update_url, {"action": "decrease"})

        response = self.client.get(reverse("cart"))

        self.assertEqual(response.context["items"][0]["quantity"], 1)
        self.assertEqual(response.context["total"], 250000)

    def test_cart_item_can_be_removed(self):
        update_url = reverse("cart_update", args=[self.product.pk])
        self.client.post(update_url, {"action": "add"})

        response = self.client.post(update_url, {"action": "remove"})

        self.assertRedirects(response, reverse("cart"))
        self.assertEqual(self.client.session.get("cart", {}), {})
        self.assertContains(self.client.get(reverse("cart")), "Savatingiz hozircha bo‘sh")

    def test_checkout_saves_order_items_and_clears_cart(self):
        customer = User.objects.create_user(username="checkoutuser", password="Uzum-checkout-pass-482!")
        wallet = Wallet.objects.create(user=customer, card_last4="9876", balance=500000)
        self.client.force_login(customer)
        update_url = reverse("cart_update", args=[self.product.pk])
        self.client.post(update_url, {"action": "add"})
        self.client.post(update_url, {"action": "increase"})

        checkout_page = self.client.get(reverse("checkout"))
        self.assertEqual(checkout_page.status_code, 200)
        self.assertContains(checkout_page, "Qabul qiluvchi ma’lumotlari")
        self.assertContains(checkout_page, "Buyurtmani tasdiqlash")

        response = self.client.post(
            reverse("checkout"),
            {
                "customer_name": "Ali Valiyev",
                "phone": "+998901234567",
                "address": "Toshkent, Chilonzor",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("order_complete"))
        order = Order.objects.get(customer_name="Ali Valiyev")
        self.assertEqual(order.total, 500000)
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, 0)
        order_item = OrderItem.objects.get(order=order)
        self.assertEqual(order_item.product, self.product)
        self.assertEqual(order_item.product_name, self.product.name)
        self.assertEqual(order_item.unit_price, 250000)
        self.assertEqual(order_item.quantity, 2)
        self.assertEqual(self.client.session.get("cart"), {})

        self.product.price = 275000
        self.product.save(update_fields=["price"])
        order_item.refresh_from_db()
        self.assertEqual(order_item.unit_price, 250000)

        confirmation = self.client.get(response.url)
        self.assertContains(confirmation, "Buyurtmangiz qabul qilindi")
        self.assertContains(confirmation, "Ali Valiyev")
        self.assertRedirects(self.client.get(reverse("order_complete")), reverse("product_list"))

    def test_checkout_applies_a_promo_code_and_credits_cashback_once(self):
        self.product.old_price = None
        self.product.save(update_fields=["old_price"])
        customer = User.objects.create_user(username="marketingbuyer")
        wallet = Wallet.objects.create(user=customer, card_last4="9876", balance=500000)
        coupon = PromoCode.objects.create(
            code="SAVE10",
            discount_type="percent",
            discount_value=10,
            max_uses=1,
        )
        self.client.force_login(customer)
        self.client.post(reverse("cart_update", args=[self.product.pk]), {"action": "add"})

        response = self.client.post(
            reverse("checkout"),
            {
                "customer_name": "Ali Valiyev",
                "phone": "+998901234567",
                "address": "Toshkent",
                "coupon_code": "save10",
            },
        )

        self.assertRedirects(response, reverse("order_complete"))
        order = Order.objects.get(user=customer)
        self.assertEqual(order.subtotal, 250000)
        self.assertEqual(order.discount_amount, 25000)
        self.assertEqual(order.total, 225000)
        self.assertEqual(order.coupon, coupon)
        self.assertEqual(order.coupon_code, "SAVE10")
        self.assertEqual(CouponRedemption.objects.get(order=order).user, customer)
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, 275000)

        self.login_as_admin()
        status_data = {"action": "update_order_status", "order_id": order.pk, "status": "completed"}
        self.client.post(reverse("dashboard"), status_data)
        self.client.post(reverse("dashboard"), status_data)
        order.refresh_from_db()
        wallet.refresh_from_db()
        self.assertEqual(order.cashback_amount, 11250)
        self.assertTrue(order.cashback_credited)
        self.assertEqual(wallet.balance, 286250)

    def test_campaign_discount_appears_in_catalog_and_prevents_coupon_stacking(self):
        self.product.old_price = None
        self.product.save(update_fields=["old_price"])
        Promotion.objects.create(
            title="Flash sale",
            product=self.product,
            image_url="https://example.com/banner.jpg",
            discount_type="percent",
            discount_value=20,
            is_flash_sale=True,
        )
        coupon = PromoCode.objects.create(
            code="EXTRA10",
            discount_type="percent",
            discount_value=10,
        )
        response = self.client.get(reverse("product_list"))
        self.assertContains(response, "Flash sale")
        self.assertContains(response, "200000")

        customer = User.objects.create_user(username="sale-buyer")
        Wallet.objects.create(user=customer, card_last4="9876", balance=500000)
        self.client.force_login(customer)
        self.client.post(reverse("cart_update", args=[self.product.pk]), {"action": "add"})
        response = self.client.post(
            reverse("checkout"),
            {
                "customer_name": "Ali Valiyev",
                "phone": "+998901234567",
                "address": "Toshkent",
                "coupon_code": coupon.code,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Promokod mahsulot chegirmalari bilan birga qo‘llanmaydi.")
        self.assertFalse(Order.objects.filter(user=customer).exists())

    def test_checkout_rejects_an_empty_cart(self):
        response = self.client.get(reverse("checkout"))

        self.assertRedirects(response, reverse("cart"))
        self.assertEqual(Order.objects.count(), 0)

    def test_discount_percentage_is_calculated(self):
        self.assertEqual(self.product.discount_percent, 17)


class AccountAuthTests(TestCase):
    def test_account_pages_render_and_google_route_is_available(self):
        register_response = self.client.get(reverse("register"))
        login_response = self.client.get(reverse("login"))

        self.assertEqual(register_response.status_code, 200)
        self.assertContains(register_response, "Hisob yaratish")
        self.assertEqual(login_response.status_code, 200)
        self.assertContains(login_response, "Hisobga kirish")
        self.assertContains(login_response, "Google orqali kirish hali sozlanmagan")
        self.assertTrue(reverse("google_login").startswith("/accounts/google/login/"))

    def test_registration_creates_account_and_logs_user_in(self):
        response = self.client.post(
            reverse("register"),
            {
                "username": "yangi_user",
                "email": "new@example.com",
                "password1": "Uzum-test-pass-482!",
                "password2": "Uzum-test-pass-482!",
            },
        )

        self.assertRedirects(response, reverse("product_list"))
        self.assertTrue(User.objects.filter(username="yangi_user").exists())
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_user_can_log_in_and_log_out(self):
        user = User.objects.create_user(username="xaridor", password="Uzum-test-pass-482!")

        response = self.client.post(
            reverse("login"),
            {"username": user.username, "password": "Uzum-test-pass-482!"},
        )
        self.assertRedirects(response, reverse("product_list"))
        self.assertTrue(response.wsgi_request.user.is_authenticated)

        response = self.client.post(reverse("logout"))
        self.assertRedirects(response, reverse("product_list"))
        self.assertFalse(response.wsgi_request.user.is_authenticated)