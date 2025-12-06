from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from claims.models import Claim, Organization, Patient
from tenancy.utils import reset_current_tenant, set_current_tenant

User = get_user_model()


class PermissionTestCase(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Org 1")

        self.admin = User.objects.create_user(
            email="admin@org.com",
            password="password",
            organization=self.org,
            role=User.Role.ADMIN,
        )
        self.processor = User.objects.create_user(
            email="proc@org.com",
            password="password",
            organization=self.org,
            role=User.Role.CLAIMS_PROCESSOR,
        )
        self.other_processor = User.objects.create_user(
            email="other@org.com",
            password="password",
            organization=self.org,
            role=User.Role.CLAIMS_PROCESSOR,
        )
        self.provider = User.objects.create_user(
            email="prov@org.com",
            password="password",
            organization=self.org,
            role=User.Role.PROVIDER,
        )

        set_current_tenant(self.org)
        self.patient = Patient.objects.create(
            first_name="P1",
            last_name="L1",
            date_of_birth="2000-01-01",
            email="p1@org.com",
        )

        self.claim = Claim.objects.create(
            patient=self.patient,
            provider=self.provider,
            assigned_processor=self.processor,
            amount=100,
            diagnosis_code="A00.0",
            submitted_date="2023-01-01",
            service_date="2023-01-01",
        )
        reset_current_tenant()

        self.client = APIClient()

    def test_processor_can_update_assigned_claim(self):
        self.client.force_login(user=self.processor)
        response = self.client.patch(
            f"/api/claims/{self.claim.id}/", {"status": "under_review"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, "under_review")

    def test_processor_cannot_update_unassigned_claim(self):
        self.client.force_login(user=self.other_processor)
        # It returns 404 because get_queryset filters it out for processors
        response = self.client.patch(
            f"/api/claims/{self.claim.id}/", {"status": "under_review"}
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_provider_cannot_update_claim(self):
        self.client.force_login(user=self.provider)
        response = self.client.patch(
            f"/api/claims/{self.claim.id}/", {"status": "under_review"}
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
