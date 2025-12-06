from tenancy.utils import reset_current_tenant, set_current_tenant


class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = None
        if request.user.is_authenticated and request.user.organization:
            token = set_current_tenant(request.user.organization)

        try:
            response = self.get_response(request)
        finally:
            if token:
                reset_current_tenant()

        return response
