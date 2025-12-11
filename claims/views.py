from django.db import transaction
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from claims.filters import ClaimFilterBackend
from claims.models import Claim, PatientStatus, User
from claims.permissions import CanManageClaim
from claims.serializers import (
    ClaimSerializer,
    ClaimStatusUpdateSerializer,
    PatientStatusSerializer,
)
from claims.tasks import (
    process_patient_admission,
    process_patient_discharge,
    process_treatment_initiated,
)


class ClaimViewSet(viewsets.ModelViewSet):
    serializer_class = ClaimSerializer
    permission_classes = [IsAuthenticated, CanManageClaim]
    filter_backends = [ClaimFilterBackend, filters.OrderingFilter]
    ordering_fields = ["service_date", "amount", "status"]
    ordering = ["-created_at"]

    def get_queryset(self):
        queryset = Claim.objects.prefetch_related("patient", "provider", "organization")
        user = self.request.user

        match user.role:
            case User.Role.CLAIMS_PROCESSOR:
                return queryset.filter(assigned_processor=user)
            case User.Role.PROVIDER:
                return queryset.filter(provider=user)
            case User.Role.PATIENT:
                return queryset.filter(patient__email=user.email)
            case _:
                return queryset

    def get_serializer_class(self):
        if self.action == "partial_update" and "status" in self.request.data:
            return ClaimStatusUpdateSerializer
        return ClaimSerializer

    @action(detail=False, methods=["post"], url_path="bulk-status-update")
    def bulk_status_update(self, request):
        claim_ids = request.data.get("claim_ids", [])
        new_status = request.data.get("status")

        if not claim_ids or not new_status:
            return Response(
                {"error": "claim_ids and status are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        updated_count = 0
        errors = []

        with transaction.atomic():
            queryset = self.get_queryset().filter(id__in=claim_ids).select_for_update()

            for claim in queryset:
                if claim.status in [Claim.Status.APPROVED, Claim.Status.PAID]:
                    errors.append(f"Claim {claim.id} is already {claim.status}")
                    continue

                claim.status = new_status
                claim.save()
                updated_count += 1

        return Response({"updated_count": updated_count, "errors": errors})


class PatientStatusViewSet(viewsets.ModelViewSet):
    serializer_class = PatientStatusSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return PatientStatus.objects.prefetch_related(
            "patient", "organization"
        ).order_by("-occurred_at")

    @action(detail=False, methods=["get"], url_path="history/(?P<patient_id>[^/.]+)")
    def history(self, request, patient_id=None):
        queryset = self.get_queryset().filter(patient__id=patient_id)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def perform_create(self, serializer):
        instance = serializer.save()

        organization_id = instance.organization.id
        patient_id = instance.patient.id

        match instance.status_type:
            case PatientStatus.StatusType.ADMISSION:
                process_patient_admission.delay_on_commit(patient_id, organization_id)
            case PatientStatus.StatusType.DISCHARGE:
                process_patient_discharge.delay_on_commit(patient_id, organization_id)
            case PatientStatus.StatusType.TREATMENT_INITIATED:
                process_treatment_initiated.delay_on_commit(
                    patient_id,
                    organization_id,
                    instance.details.get("treatment_type", "N/A"),
                )
            case _:
                return None
