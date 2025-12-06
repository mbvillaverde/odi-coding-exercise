from rest_framework import filters


class ClaimFilterBackend(filters.BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        from_date = request.query_params.get("from_date")
        to_date = request.query_params.get("to_date")

        if from_date:
            queryset = queryset.filter(service_date__gte=from_date)

        if to_date:
            queryset = queryset.filter(service_date__lte=to_date)

        status = request.query_params.get("status")
        if status:
            queryset = queryset.filter(status=status)

        patient_id = request.query_params.get("patient_id")
        if patient_id:
            queryset = queryset.filter(patient__id=patient_id)

        provider_id = request.query_params.get("provider_id")
        if provider_id:
            queryset = queryset.filter(provider__id=provider_id)

        min_amount = request.query_params.get("min_amount")
        max_amount = request.query_params.get("max_amount")

        if min_amount:
            queryset = queryset.filter(amount__gte=min_amount)

        if max_amount:
            queryset = queryset.filter(amount__lte=max_amount)

        return queryset
