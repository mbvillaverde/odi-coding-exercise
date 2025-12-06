import uuid

from django.contrib.auth.models import AbstractBaseUser
from django.db import models

from tenancy.models import TenantModel, TenantUserManager


class User(AbstractBaseUser, TenantModel):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        CLAIMS_PROCESSOR = "claims_processor", "Claims Processor"
        PROVIDER = "provider", "Provider"
        PATIENT = "patient", "Patient"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.PATIENT)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["role"]

    def __str__(self):
        return f"<User {self.id}: {self.email}>"


class Patient(TenantModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    date_of_birth = models.DateField()
    email = models.EmailField()
    phone = models.CharField(max_length=50)

    def __str__(self):
        return f"<Patient {self.id}: {self.email}>"


class Claim(TenantModel):
    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        UNDER_REVIEW = "under_review", "Under Review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        PAID = "paid", "Paid"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    provider = models.ForeignKey(
        User, related_name="provider_claims", on_delete=models.CASCADE
    )
    assigned_processor = models.ForeignKey(
        User,
        null=True,
        blank=True,
        related_name="assigned_claims",
        on_delete=models.SET_NULL,
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.SUBMITTED
    )
    diagnosis_code = models.CharField(max_length=20)
    procedure_code = models.CharField(max_length=20, null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    submitted_date = models.DateField()
    service_date = models.DateField()
    approval_reason = models.TextField(null=True, blank=True)
    rejection_reason = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"<Claim {self.id}: {self.diagnosis_code} | {self.procedure_code} | {self.status}>"


class PatientStatus(TenantModel):
    class StatusType(models.TextChoices):
        ADMISSION = "admission", "Admission"
        DISCHARGE = "discharge", "Discharge"
        TREATMENT_INITIATED = "treatment_initiated", "Treatment Initiated"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    status_type = models.CharField(max_length=50, choices=StatusType.choices)
    facility_name = models.CharField(max_length=255, null=True, blank=True)
    details = models.JSONField(default=dict)
    occurred_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"<PatientStatus {self.id}: {self.patient} | {self.status_type}>"
