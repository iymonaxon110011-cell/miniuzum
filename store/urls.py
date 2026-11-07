from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from .forms import LoginForm


urlpatterns = [
    path("", views.product_list, name="product_list"),
    path("sevimlilar/", views.wishlist, name="wishlist"),
    path("sevimlilar/<int:pk>/", views.wishlist_toggle, name="wishlist_toggle"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("register/", views.register, name="register"),
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="store/auth_form.html",
            authentication_form=LoginForm,
            extra_context={"is_register": False},
        ),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("mahsulot/qoshish/", views.product_create, name="product_create"),
    path("mahsulot/<int:pk>/", views.product_detail, name="product_detail"),
    path("mahsulot/<int:pk>/tahrirlash/", views.product_update, name="product_update"),
    path("mahsulot/<int:pk>/ochirish/", views.product_delete, name="product_delete"),
    path("savat/", views.cart, name="cart"),
    path("savat/mahsulot/<int:pk>/", views.cart_update, name="cart_update"),
    path("buyurtma/", views.checkout, name="checkout"),
    path("buyurtma/tasdiq/", views.order_complete, name="order_complete"),
    path("profil/", views.profile, name="profile"),
    path("profil/balans-holati/", views.topup_status, name="topup_status"),
]