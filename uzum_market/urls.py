from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from django.views.static import serve


handler404 = "store.views.page_not_found"

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("", include("store.urls")),
]

media_path = f"{settings.MEDIA_URL.lstrip('/')}<path:path>"
urlpatterns.append(path(media_path, serve, {"document_root": settings.MEDIA_ROOT}))

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)