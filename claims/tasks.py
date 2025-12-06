import logging

from celery import shared_task
from django.db import transaction

from claims.models import Claim

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def process_patient_admission(patient_id, organization_id):
    with transaction.atomic():
        # Find all submitted claims for patient
        claims = Claim.objects.filter(
            patient_id=patient_id,
            organization_id=organization_id,
            status=Claim.Status.SUBMITTED,
        ).select_for_update()

        # Mark them as under review
        count = claims.update(status=Claim.Status.UNDER_REVIEW)

        # Log what happened
        logger.info(f"Set {count} claims as UNDER_REVIEW for patient {patient_id}")


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def process_patient_discharge(patient_id, organization_id):
    with transaction.atomic():
        # Find all pending (submitted, under review) claims for patient
        claims = Claim.objects.filter(
            patient_id=patient_id,
            organization_id=organization_id,
            status__in=[Claim.Status.SUBMITTED, Claim.Status.UNDER_REVIEW],
        ).select_for_update()

        # Move to approved (auto-finalize)
        count = claims.update(
            status=Claim.Status.APPROVED, approval_reason="Auto-finalize"
        )

        # Log what happened
        logger.info(f"Set {count} claims as APPROVED for patient {patient_id}")


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def process_treatment_initiated(patient_id, organization_id, treatment_type):
    with transaction.atomic():
        # Find related claims (assuming all submitted claims)
        claims = Claim.objects.filter(
            patient_id=patient_id,
            organization_id=organization_id,
            status=Claim.Status.SUBMITTED,
        ).select_for_update()

        # Update status (assumed that all submitted claims will be set into under review)
        count = claims.update(status=Claim.Status.UNDER_REVIEW)

        # Log what happened
        logger.info(
            f"Treatment {treatment_type}: Set {count} claims as UNDER_REVIEW for patient {patient_id}"
        )
