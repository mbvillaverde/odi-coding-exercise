from rest_framework import serializers

from claims.models import Claim, Patient, PatientStatus, User
from claims.validators import validate_diagnosis_code, validate_procedure_code


class PatientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Patient
        fields = "__all__"
        read_only_fields = ("organization",)


class ClaimSerializer(serializers.ModelSerializer):
    diagnosis_code = serializers.CharField(validators=[validate_diagnosis_code])
    procedure_code = serializers.CharField(validators=[validate_procedure_code])
    amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=1, max_value=10_000_000
    )
    patient_details = serializers.SerializerMethodField()

    class Meta:
        model = Claim
        fields = "__all__"
        read_only_fields = (
            "organization",
            "created_at",
            "updated_at",
            "status",
            "patient_details",
        )

    def get_patient_details(self, instance):
        # NOTE: To create a nested details for foreign object, use SerializerMethodField
        #       combined with Model Serializer
        return PatientSerializer(instance.patient).data


class ClaimStatusUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Claim
        fields = ("status", "approval_reason", "rejection_reason")

    def validate_status(self, value):
        if self.instance and self.instance.status in [
            Claim.Status.APPROVED,
            Claim.Status.PAID,
        ]:
            raise serializers.ValidationError("Cannot modify approved or paid claims.")
        return value

    def validate(self, data):
        user = self.context["request"].user
        if user.role != User.Role.CLAIMS_PROCESSOR:
            raise serializers.ValidationError("Only claims processor can update claim.")

        return data


class PatientStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = PatientStatus
        fields = "__all__"
        read_only_fields = ("organization", "created_at")
