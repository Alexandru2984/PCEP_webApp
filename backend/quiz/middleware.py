from django.core.exceptions import RequestDataTooBig
from django.http import JsonResponse


class APIResponseMiddleware:
    """Keep grading feedback out of browser/proxy caches, including errors."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/api/'):
            try:
                # Force Django's upload bound before DRF streams the JSON body.
                request.body
            except RequestDataTooBig:
                response = JsonResponse({'detail': 'Request body is too large.'}, status=413)
            else:
                response = self.get_response(request)
            response['Cache-Control'] = 'no-store'
            return response
        return self.get_response(request)
