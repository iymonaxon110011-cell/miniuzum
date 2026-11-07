from pathlib import Path
import re

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.core.files.storage import default_storage

from .models import Product, ProductReview, Promotion, PromoCode


class RegisterForm(UserCreationForm):
    email = forms.EmailField(label="Elektron pochta", required=True)

    class Meta:
        model = User
        fields = ("username", "email")
        labels = {"username": "Foydalanuvchi nomi"}
        widgets = {
            "username": forms.TextInput(attrs={"autocomplete": "username"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].label = "Parol"
        self.fields["password1"].widget.attrs["autocomplete"] = "new-password"
        self.fields["password2"].label = "Parolni tasdiqlang"
        self.fields["password2"].widget.attrs["autocomplete"] = "new-password"


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label="Foydalanuvchi nomi",
        widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username"}),
    )
    password = forms.CharField(
        label="Parol",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )


class CheckoutForm(forms.Form):
    customer_name = forms.CharField(
        label="Ism va familiya",
        max_length=120,
        widget=forms.TextInput(attrs={"autocomplete": "name", "placeholder": "Ism va familiyangiz"}),
    )
    phone = forms.CharField(
        label="Telefon raqami",
        max_length=30,
        widget=forms.TelInput(attrs={"autocomplete": "tel", "placeholder": "+998 90 123 45 67"}),
    )
    address = forms.CharField(
        label="Yetkazish manzili",
        max_length=255,
        widget=forms.Textarea(attrs={"autocomplete": "street-address", "placeholder": "Manzilni kiriting", "rows": 3}),
    )
    coupon_code = forms.CharField(
        label="Promokod yoki kupon",
        required=False,
        max_length=32,
        widget=forms.TextInput(attrs={"autocomplete": "off", "placeholder": "Masalan, YANGI10"}),
    )


class CardNumberForm(forms.Form):
    card_number = forms.RegexField(
        regex=re.compile(r"^[0-9]{16}$"),
        min_length=16,
        max_length=16,
        label="Karta raqami",
        error_messages={"invalid": "Karta raqami 16 ta raqamdan iborat bo‘lishi kerak."},
        widget=forms.TextInput(attrs={
            "inputmode": "numeric",
            "autocomplete": "off",
            "maxlength": "16",
            "pattern": "[0-9]{16}",
            "placeholder": "0000000000000000",
        }),
    )


class TopUpForm(forms.Form):
    amount = forms.DecimalField(
        label="To‘ldirish summasi",
        min_value=1000,
        max_digits=12,
        decimal_places=0,
        widget=forms.NumberInput(attrs={"min": "1000", "step": "1000", "placeholder": "100000"}),
    )


class ProductReviewForm(forms.ModelForm):
    class Meta:
        model = ProductReview
        fields = ["rating", "comment"]
        widgets = {
            "rating": forms.Select(),
            "comment": forms.Textarea(attrs={
                "rows": 4,
                "maxlength": "1000",
                "placeholder": "Mahsulot haqidagi haqiqiy fikringizni yozing",
            }),
        }


class ProductForm(forms.ModelForm):
    category = forms.CharField(
        label="Kategoriya",
        max_length=40,
        initial="Boshqa",
        widget=forms.TextInput(attrs={
            "list": "product-category-options",
            "placeholder": "Masalan, Kiyim",
        }),
    )
    image = forms.ImageField(
        label="Mahsulot rasmi",
        required=False,
        widget=forms.ClearableFileInput(attrs={"accept": "image/*", "class": "upload-input"}),
    )

    class Meta:
        model = Product
        fields = ["name", "brand", "category", "color", "season", "price", "old_price", "description"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Masalan, simsiz quloqchin"}),
            "brand": forms.TextInput(attrs={"placeholder": "Masalan, Samsung"}),
            "season": forms.Select(attrs={"data-product-season": ""}),
            "price": forms.NumberInput(attrs={"placeholder": "249000", "min": "0"}),
            "old_price": forms.NumberInput(attrs={"placeholder": "299000", "min": "0"}),
            "description": forms.Textarea(attrs={"placeholder": "Mahsulot haqida qisqacha...", "rows": 4}),
        }

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("category") != "Kiyim":
            cleaned_data["season"] = ""
        price = cleaned_data.get("price")
        old_price = cleaned_data.get("old_price")
        if price is not None and old_price is not None and old_price <= price:
            self.add_error("old_price", "Eski narx joriy narxdan yuqori bo'lishi kerak.")
        return cleaned_data

    def clean_category(self):
        return self.cleaned_data["category"].strip()

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if image and image.size > 10 * 1024 * 1024:
            raise forms.ValidationError("Rasm hajmi 10 MB dan oshmasligi kerak.")
        return image

    def save(self, commit=True):
        product = super().save(commit=False)
        image = self.cleaned_data.get("image")
        if image:
            image_name = Path(image.name).name
            saved_name = default_storage.save(f"products/{image_name}", image)
            product.image_url = default_storage.url(saved_name)
        if commit:
            product.save()
        return product


class PromotionForm(forms.ModelForm):
    image = forms.ImageField(
        label="Aksiya rasmi",
        widget=forms.ClearableFileInput(attrs={"accept": "image/*"}),
    )

    class Meta:
        model = Promotion
        fields = [
            "title", "subtitle", "category", "product", "discount_label",
            "discount_type", "discount_value", "starts_at", "ends_at",
            "is_flash_sale", "is_active",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Masalan, Haftaning eng yaxshi taklifi"}),
            "subtitle": forms.TextInput(attrs={"placeholder": "Aksiya haqida qisqacha"}),
            "category": forms.Select(),
            "product": forms.Select(),
            "discount_label": forms.TextInput(attrs={"placeholder": "−25%"}),
            "discount_value": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
            "starts_at": forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}),
            "ends_at": forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].required = False
        self.fields["category"].label = "Maqsadli turkum (ixtiyoriy)"
        self.fields["product"].label = "Maqsadli mahsulot (ixtiyoriy)"
        self.fields["product"].queryset = Product.objects.filter(is_approved=True).order_by("name")
        self.fields["product"].empty_label = "Butun turkumga yo‘naltirish"
        self.fields["discount_type"].required = False
        self.fields["discount_value"].required = False
        for field_name in ("starts_at", "ends_at"):
            self.fields[field_name].input_formats = ["%Y-%m-%dT%H:%M"]

    def clean_discount_type(self):
        return self.cleaned_data.get("discount_type") or "percent"

    def clean_discount_value(self):
        return self.cleaned_data.get("discount_value") or 0

    def clean(self):
        cleaned_data = super().clean()
        value = cleaned_data.get("discount_value")
        discount_type = cleaned_data.get("discount_type")
        product = cleaned_data.get("product")
        category = cleaned_data.get("category")
        starts_at = cleaned_data.get("starts_at")
        ends_at = cleaned_data.get("ends_at")
        if value is not None and value < 0:
            self.add_error("discount_value", "Chegirma manfiy bo‘lishi mumkin emas.")
        if value and discount_type == "percent" and value > 100:
            self.add_error("discount_value", "Foizli chegirma 100% dan oshmasligi kerak.")
        if value and not (product or category):
            self.add_error("product", "Chegirma uchun mahsulot yoki turkum tanlang.")
        if starts_at and ends_at and starts_at >= ends_at:
            self.add_error("ends_at", "Tugash vaqti boshlanish vaqtidan keyin bo‘lishi kerak.")
        if cleaned_data.get("is_flash_sale"):
            if not ends_at:
                self.add_error("ends_at", "Flash sale uchun tugash vaqtini kiriting.")
            if not value:
                self.add_error("discount_value", "Flash sale uchun chegirma miqdorini kiriting.")
        return cleaned_data

    def clean_image(self):
        image = self.cleaned_data["image"]
        if image.size > 10 * 1024 * 1024:
            raise forms.ValidationError("Rasm hajmi 10 MB dan oshmasligi kerak.")
        return image

    def save(self, commit=True):
        promotion = super().save(commit=False)
        image = self.cleaned_data["image"]
        image_name = Path(image.name).name
        saved_name = default_storage.save(f"promotions/{image_name}", image)
        promotion.image_url = default_storage.url(saved_name)
        if commit:
            promotion.save()
        return promotion


class PromoCodeForm(forms.ModelForm):
    class Meta:
        model = PromoCode
        fields = [
            "code", "discount_type", "discount_value", "minimum_order",
            "starts_at", "ends_at", "max_uses", "is_active",
        ]
        widgets = {
            "code": forms.TextInput(attrs={"placeholder": "Masalan, YANGI10", "autocapitalize": "characters"}),
            "discount_value": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
            "minimum_order": forms.NumberInput(attrs={"min": "0", "step": "1000"}),
            "starts_at": forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}),
            "ends_at": forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}),
            "max_uses": forms.NumberInput(attrs={"min": "1", "placeholder": "Cheklanmagan"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["max_uses"].required = False
        for field_name in ("starts_at", "ends_at"):
            self.fields[field_name].required = False
            self.fields[field_name].input_formats = ["%Y-%m-%dT%H:%M"]

    def clean_code(self):
        return self.cleaned_data["code"].strip().upper()

    def clean(self):
        cleaned_data = super().clean()
        value = cleaned_data.get("discount_value")
        discount_type = cleaned_data.get("discount_type")
        starts_at = cleaned_data.get("starts_at")
        ends_at = cleaned_data.get("ends_at")
        if value is not None and value <= 0:
            self.add_error("discount_value", "Chegirma miqdori noldan katta bo‘lishi kerak.")
        if value and discount_type == "percent" and value > 100:
            self.add_error("discount_value", "Foizli chegirma 100% dan oshmasligi kerak.")
        if starts_at and ends_at and starts_at >= ends_at:
            self.add_error("ends_at", "Tugash vaqti boshlanish vaqtidan keyin bo‘lishi kerak.")
        return cleaned_data