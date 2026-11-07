from .services import generate_daily_product_suggestion


class DailyProductSuggestionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method in ("GET", "HEAD") and not request.path.startswith("/admin/"):
            generate_daily_product_suggestion()
        return self.get_response(request)


