from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from claims.models import Claim, Organization, Patient
from tenancy.utils import reset_current_tenant, set_current_tenant

User = get_user_model()


class TenancyTestCase(TestCase):
    def setUp(self):
        self.org1 = Organization.objects.create(name="Org 1")
        self.org2 = Organization.objects.create(name="Org 2")

        self.user1 = User.objects.create_user(
            email="user1@org1.com",
            password="password",
            organization=self.org1,
            role=User.Role.ADMIN,
        )
        self.user2 = User.objects.create_user(
            email="user2@org2.com",
            password="password",
            organization=self.org2,
            role=User.Role.ADMIN,
        )

        # Create data for Org 1
        set_current_tenant(self.org1)
        self.patient1 = Patient.objects.create(
            first_name="P1",
            last_name="L1",
            date_of_birth="2000-01-01",
            email="p1@org1.com",
        )
        self.claim1 = Claim.objects.create(
            patient=self.patient1,
            provider=self.user1,
            amount=100,
            diagnosis_code="A00.0",
            submitted_date="2023-01-01",
            service_date="2023-01-01",
        )
        reset_current_tenant()

        # Create data for Org 2
        set_current_tenant(self.org2)
        self.patient2 = Patient.objects.create(
            first_name="P2",
            last_name="L2",
            date_of_birth="2000-01-01",
            email="p2@org2.com",
        )
        self.claim2 = Claim.objects.create(
            patient=self.patient2,
            provider=self.user2,
            amount=200,
            diagnosis_code="B00.0",
            submitted_date="2023-01-01",
            service_date="2023-01-01",
        )
        reset_current_tenant()

        self.client = APIClient()

    def test_tenant_isolation_queryset(self):
        # Simulate request from User 1
        self.client.force_login(user=self.user1)
        response = self.client.get("/api/claims/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["id"], str(self.claim1.id))

        # Simulate request from User 2
        self.client.force_login(user=self.user2)
        response = self.client.get("/api/claims/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["id"], str(self.claim2.id))

    def test_cross_tenant_access_denied(self):
        # User 1 tries to access Claim 2
        self.client.force_login(user=self.user1)
        response = self.client.get(f"/api/claims/{self.claim2.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_claim_sets_tenant(self):
        self.client.force_login(user=self.user1)
        data = {
            "patient": self.patient1.id,
            "provider": self.user1.id,
            "amount": "150.00",
            "diagnosis_code": "C00.0",
            "submitted_date": "2023-01-02",
            "service_date": "2023-01-02",
        }
        response = self.client.post("/api/claims/", data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        claim_id = response.data["id"]

        # Verify it belongs to Org 1
        set_current_tenant(self.org1)
        claim = Claim.objects.get(id=claim_id)
        self.assertEqual(claim.organization, self.org1)
        reset_current_tenant()
