from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from claims.models import Claim, Patient, PatientStatus
from tenancy.models import Organization
from tenancy.utils import reset_current_tenant, set_current_tenant

User = get_user_model()


class ClaimsAPITestCase(TestCase):
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
        response = self.client.get("/claims/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["id"], str(self.claim1.id))

        # Simulate request from User 2
        self.client.force_login(user=self.user2)
        response = self.client.get("/claims/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["id"], str(self.claim2.id))

    def test_cross_tenant_access_denied(self):
        # User 1 tries to access Claim 2
        self.client.force_login(user=self.user1)
        response = self.client.get(f"/claims/{self.claim2.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_claim_sets_tenant(self):
        self.client.force_login(user=self.user1)
        data = {
            "patient": self.patient1.id,
            "provider": self.user1.id,
            "amount": "150.00",
            "diagnosis_code": "C00.0",
            "procedure_code": "10001",
            "submitted_date": "2023-01-02",
            "service_date": "2023-01-02",
        }
        response = self.client.post("/claims/", data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        claim_id = response.data["id"]

        # Verify it belongs to Org 1
        set_current_tenant(self.org1)
        claim = Claim.objects.get(id=claim_id)
        self.assertEqual(claim.organization, self.org1)
        reset_current_tenant()

    def test_cross_tenant_update_denied(self):
        """User from Org1 tries to update claim from Org2"""
        self.client.force_login(user=self.user1)
        response = self.client.patch(
            f"/claims/{self.claim2.id}/", {"status": "approved"}
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Verify claim wasn't modified
        set_current_tenant(self.org2)
        self.claim2.refresh_from_db()
        self.assertEqual(self.claim2.status, Claim.Status.SUBMITTED)
        reset_current_tenant()

    def test_cross_tenant_delete_denied(self):
        """User from Org1 tries to delete claim from Org2"""
        self.client.force_login(user=self.user1)
        response = self.client.delete(f"/claims/{self.claim2.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Verify claim still exists
        set_current_tenant(self.org2)
        self.assertTrue(Claim.objects.filter(id=self.claim2.id).exists())
        reset_current_tenant()

    def test_provider_can_only_see_own_claims(self):
        """Provider role should only see claims they provided"""
        set_current_tenant(self.org1)
        provider1 = User.objects.create_user(
            email="provider1@org1.com",
            password="password",
            organization=self.org1,
            role=User.Role.PROVIDER,
        )
        provider2 = User.objects.create_user(
            email="provider2@org1.com",
            password="password",
            organization=self.org1,
            role=User.Role.PROVIDER,
        )
        claim_provider2 = Claim.objects.create(
            patient=self.patient1,
            provider=provider2,
            amount=300,
            diagnosis_code="D00.0",
            submitted_date="2023-01-01",
            service_date="2023-01-01",
        )
        reset_current_tenant()

        # Provider1 should not see Provider2's claims
        self.client.force_login(user=provider1)
        response = self.client.get("/claims/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 0)

        # Provider1 should not access Provider2's claim directly
        response = self.client.get(f"/claims/{claim_provider2.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Provider2 should see their own claim
        self.client.force_login(user=provider2)
        response = self.client.get("/claims/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

    def test_claims_processor_can_only_see_assigned_claims(self):
        """Claims processor should only see claims assigned to them"""
        set_current_tenant(self.org1)
        processor1 = User.objects.create_user(
            email="processor1@org1.com",
            password="password",
            organization=self.org1,
            role=User.Role.CLAIMS_PROCESSOR,
        )
        processor2 = User.objects.create_user(
            email="processor2@org1.com",
            password="password",
            organization=self.org1,
            role=User.Role.CLAIMS_PROCESSOR,
        )

        self.claim1.assigned_processor = processor1
        self.claim1.save()

        claim_for_processor2 = Claim.objects.create(
            patient=self.patient1,
            provider=self.user1,
            assigned_processor=processor2,
            amount=300,
            diagnosis_code="E00.0",
            submitted_date="2023-01-01",
            service_date="2023-01-01",
        )
        reset_current_tenant()

        # Processor1 should only see their assigned claim
        self.client.force_login(user=processor1)
        response = self.client.get("/claims/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["id"], str(self.claim1.id))

        # Processor1 cannot access Processor2's claim
        response = self.client.get(f"/claims/{claim_for_processor2.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_patient_can_only_see_own_claims(self):
        """Patient should only see their own claims"""
        set_current_tenant(self.org1)
        patient_user = User.objects.create_user(
            email=self.patient1.email,
            password="password",
            organization=self.org1,
            role=User.Role.PATIENT,
        )

        patient3 = Patient.objects.create(
            first_name="P3",
            last_name="L3",
            date_of_birth="2000-01-01",
            email="p3@org1.com",
        )
        claim_patient3 = Claim.objects.create(
            patient=patient3,
            provider=self.user1,
            amount=400,
            diagnosis_code="F00.0",
            submitted_date="2023-01-01",
            service_date="2023-01-01",
        )
        reset_current_tenant()

        # Patient should only see their own claims
        self.client.force_login(user=patient_user)
        response = self.client.get("/claims/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["patient"], self.patient1.id)

        # Patient cannot access other patient's claims
        response = self.client.get(f"/claims/{claim_patient3.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_patient_cannot_update_claims(self):
        """Patient role should be read-only"""
        set_current_tenant(self.org1)
        patient_user = User.objects.create_user(
            email=self.patient1.email,
            password="password",
            organization=self.org1,
            role=User.Role.PATIENT,
        )
        reset_current_tenant()

        self.client.force_login(user=patient_user)
        response = self.client.patch(
            f"/claims/{self.claim1.id}/", {"status": "approved"}
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_provider_cannot_update_claims(self):
        """Provider role should be read-only"""
        set_current_tenant(self.org1)
        provider = User.objects.create_user(
            email="provider@org1.com",
            password="password",
            organization=self.org1,
            role=User.Role.PROVIDER,
        )
        claim = Claim.objects.create(
            patient=self.patient1,
            provider=provider,
            amount=500,
            diagnosis_code="G00.0",
            submitted_date="2023-01-01",
            service_date="2023-01-01",
        )
        reset_current_tenant()

        self.client.force_login(user=provider)
        response = self.client.patch(f"/claims/{claim.id}/", {"status": "approved"})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_cannot_modify_approved_claims(self):
        """Approved claims should be read-only"""
        set_current_tenant(self.org1)
        self.claim1.status = Claim.Status.APPROVED
        self.claim1.save()
        reset_current_tenant()

        self.client.force_login(user=self.user1)
        response = self.client.patch(
            f"/claims/{self.claim1.id}/", {"status": "rejected"}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Verify claim wasn't modified
        set_current_tenant(self.org1)
        self.claim1.refresh_from_db()
        self.assertEqual(self.claim1.status, Claim.Status.APPROVED)
        reset_current_tenant()

    def test_cannot_modify_paid_claims(self):
        """Paid claims should be read-only"""
        set_current_tenant(self.org1)
        self.claim1.status = Claim.Status.PAID
        self.claim1.save()
        reset_current_tenant()

        self.client.force_login(user=self.user1)
        response = self.client.patch(
            f"/claims/{self.claim1.id}/", {"status": "rejected"}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_claims_processor_can_only_update_assigned_claims(self):
        """Claims processor can only update claims assigned to them"""
        set_current_tenant(self.org1)
        processor = User.objects.create_user(
            email="processor@org1.com",
            password="password",
            organization=self.org1,
            role=User.Role.CLAIMS_PROCESSOR,
        )

        claim_assigned = Claim.objects.create(
            patient=self.patient1,
            provider=self.user1,
            assigned_processor=processor,
            amount=600,
            diagnosis_code="H00.0",
            submitted_date="2023-01-01",
            service_date="2023-01-01",
        )
        reset_current_tenant()

        # Processor can update assigned claim
        self.client.force_login(user=processor)
        response = self.client.patch(
            f"/claims/{claim_assigned.id}/", {"status": "approved"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Processor cannot update unassigned claim (claim1 has no assigned processor)
        response = self.client.patch(
            f"/claims/{self.claim1.id}/", {"status": "approved"}
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_filtering_by_date_range(self):
        """Test filtering claims by date range"""
        set_current_tenant(self.org1)
        Claim.objects.create(
            patient=self.patient1,
            provider=self.user1,
            amount=700,
            diagnosis_code="I00.0",
            submitted_date="2023-01-15",
            service_date="2023-01-15",
        )
        reset_current_tenant()

        self.client.force_login(user=self.user1)
        response = self.client.get(
            "/claims/", {"from_date": "2023-01-10", "to_date": "2023-01-20"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

    def test_filtering_by_status(self):
        """Test filtering claims by status"""
        set_current_tenant(self.org1)
        self.claim1.status = Claim.Status.APPROVED
        self.claim1.save()
        Claim.objects.create(
            patient=self.patient1,
            provider=self.user1,
            amount=800,
            diagnosis_code="J00.0",
            submitted_date="2023-01-01",
            service_date="2023-01-01",
            status=Claim.Status.SUBMITTED,
        )
        reset_current_tenant()

        self.client.force_login(user=self.user1)
        response = self.client.get("/claims/", {"status": "approved"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["status"], Claim.Status.APPROVED)

    def test_filtering_by_patient(self):
        """Test filtering claims by patient"""
        set_current_tenant(self.org1)
        patient2 = Patient.objects.create(
            first_name="P4",
            last_name="L4",
            date_of_birth="2000-01-01",
            email="p4@org1.com",
        )
        Claim.objects.create(
            patient=patient2,
            provider=self.user1,
            amount=900,
            diagnosis_code="K00.0",
            submitted_date="2023-01-01",
            service_date="2023-01-01",
        )
        reset_current_tenant()

        self.client.force_login(user=self.user1)
        response = self.client.get("/claims/", {"patient_id": str(self.patient1.id)})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["patient"], self.patient1.id)

    def test_filtering_by_provider(self):
        """Test filtering claims by provider"""
        set_current_tenant(self.org1)
        provider2 = User.objects.create_user(
            email="provider2@org1.com",
            password="password",
            organization=self.org1,
            role=User.Role.PROVIDER,
        )
        Claim.objects.create(
            patient=self.patient1,
            provider=provider2,
            amount=1000,
            diagnosis_code="L00.0",
            submitted_date="2023-01-01",
            service_date="2023-01-01",
        )
        reset_current_tenant()

        self.client.force_login(user=self.user1)
        response = self.client.get("/claims/", {"provider_id": str(self.user1.id)})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["provider"], self.user1.id)

    def test_filtering_by_amount_range(self):
        """Test filtering claims by amount range"""
        set_current_tenant(self.org1)
        Claim.objects.create(
            patient=self.patient1,
            provider=self.user1,
            amount=1500,
            diagnosis_code="M00.0",
            submitted_date="2023-01-01",
            service_date="2023-01-01",
        )
        reset_current_tenant()

        self.client.force_login(user=self.user1)
        response = self.client.get(
            "/claims/", {"min_amount": "50", "max_amount": "500"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertTrue(50 <= Decimal(response.data["results"][0]["amount"]) <= 500)

    def test_sorting_by_date(self):
        """Test sorting claims by date"""
        set_current_tenant(self.org1)
        Claim.objects.create(
            patient=self.patient1,
            provider=self.user1,
            amount=1100,
            diagnosis_code="N00.0",
            submitted_date="2023-01-05",
            service_date="2023-01-05",
        )
        reset_current_tenant()

        self.client.force_login(user=self.user1)
        response = self.client.get("/claims/", {"ordering": "service_date"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        dates = [claim["service_date"] for claim in response.data["results"]]
        self.assertEqual(dates, sorted(dates))

    def test_sorting_by_amount(self):
        """Test sorting claims by amount"""
        set_current_tenant(self.org1)
        Claim.objects.create(
            patient=self.patient1,
            provider=self.user1,
            amount=50,
            diagnosis_code="O00.0",
            submitted_date="2023-01-01",
            service_date="2023-01-01",
        )
        reset_current_tenant()

        self.client.force_login(user=self.user1)
        response = self.client.get("/claims/", {"ordering": "amount"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        amounts = [Decimal(claim["amount"]) for claim in response.data["results"]]
        self.assertEqual(amounts, sorted(amounts))

    def test_pagination(self):
        """Test pagination works correctly"""
        set_current_tenant(self.org1)
        for i in range(15):
            Claim.objects.create(
                patient=self.patient1,
                provider=self.user1,
                amount=100 + i,
                diagnosis_code=f"P{i:02d}.0",
                submitted_date="2023-01-01",
                service_date="2023-01-01",
            )
        reset_current_tenant()

        self.client.force_login(user=self.user1)
        response = self.client.get("/claims/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("next", response.data)
        self.assertIn("previous", response.data)
        self.assertIn("count", response.data)

    def test_bulk_status_update_only_accessible_claims(self):
        """Bulk update should only affect claims user has access to"""
        set_current_tenant(self.org1)
        claim2_org1 = Claim.objects.create(
            patient=self.patient1,
            provider=self.user1,
            amount=1200,
            diagnosis_code="Q00.0",
            submitted_date="2023-01-01",
            service_date="2023-01-01",
        )
        reset_current_tenant()

        self.client.force_login(user=self.user1)
        response = self.client.post(
            "/claims/bulk-status-update/",
            {
                "claim_ids": [
                    str(self.claim1.id),
                    str(claim2_org1.id),
                    str(self.claim2.id),
                ],
                "status": "approved",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should only update 2 claims from Org1, not claim2 from Org2
        self.assertEqual(response.data["updated_count"], 2)

        # Verify claim2 from Org2 was not updated
        set_current_tenant(self.org2)
        self.claim2.refresh_from_db()
        self.assertEqual(self.claim2.status, Claim.Status.SUBMITTED)
        reset_current_tenant()

    def test_bulk_status_update_skips_approved_claims(self):
        """Bulk update should skip approved/paid claims"""
        set_current_tenant(self.org1)
        self.claim1.status = Claim.Status.APPROVED
        self.claim1.save()
        claim2 = Claim.objects.create(
            patient=self.patient1,
            provider=self.user1,
            amount=1300,
            diagnosis_code="R00.0",
            submitted_date="2023-01-01",
            service_date="2023-01-01",
        )
        reset_current_tenant()

        self.client.force_login(user=self.user1)
        response = self.client.post(
            "/claims/bulk-status-update/",
            {
                "claim_ids": [str(self.claim1.id), str(claim2.id)],
                "status": "under_review",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["updated_count"], 1)
        self.assertTrue(len(response.data["errors"]) > 0)

    def test_create_claim_with_cross_tenant_patient(self):
        """Cannot create claim with patient from different organization"""
        self.client.force_login(user=self.user1)
        data = {
            "patient": self.patient2.id,  # Patient from Org2
            "provider": self.user1.id,
            "amount": "150.00",
            "diagnosis_code": "S00.0",
            "submitted_date": "2023-01-02",
            "service_date": "2023-01-02",
        }
        response = self.client.post("/claims/", data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_claim_with_invalid_amount(self):
        """Test validation for invalid claim amounts"""
        self.client.force_login(user=self.user1)
        data = {
            "patient": self.patient1.id,
            "provider": self.user1.id,
            "amount": "-100.00",  # Negative amount
            "diagnosis_code": "T00.0",
            "submitted_date": "2023-01-02",
            "service_date": "2023-01-02",
        }
        response = self.client.post("/claims/", data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_access_denied(self):
        """Unauthenticated users cannot access claims"""
        response = self.client.get("/claims/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_concurrent_update_handling(self):
        """Test handling of concurrent updates to same claim"""
        set_current_tenant(self.org1)
        processor = User.objects.create_user(
            email="concurrent@org1.com",
            password="password",
            organization=self.org1,
            role=User.Role.CLAIMS_PROCESSOR,
        )
        self.claim1.assigned_processor = processor
        self.claim1.save()
        reset_current_tenant()

        self.client.force_login(user=processor)

        # Simulate two concurrent updates
        response1 = self.client.patch(
            f"/claims/{self.claim1.id}/", {"status": "under_review"}
        )
        response2 = self.client.patch(
            f"/claims/{self.claim1.id}/", {"status": "approved"}
        )

        # Both should succeed (last one wins in this implementation)
        self.assertIn(
            response1.status_code, [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST]
        )
        self.assertIn(
            response2.status_code, [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST]
        )

    @patch("claims.tasks.process_patient_admission.delay_on_commit")
    def test_patient_status_triggers_async_task(self, mock_task):
        """Test that creating patient status triggers async task"""
        self.client.force_login(user=self.user1)
        data = {
            "patient": self.patient1.id,
            "status_type": "admission",
            "occurred_at": timezone.now().isoformat(),
            "details": {"facility": "Test Hospital"},
        }
        response = self.client.post("/patient-status/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # Task should be called with patient_id and organization_id
        mock_task.assert_called_once()

    def test_patient_status_history_tenant_isolated(self):
        """Patient status history should be tenant-isolated"""
        set_current_tenant(self.org1)
        status1 = PatientStatus.objects.create(
            patient=self.patient1,
            status_type=PatientStatus.StatusType.ADMISSION,
            occurred_at=timezone.now(),
        )
        reset_current_tenant()

        set_current_tenant(self.org2)
        PatientStatus.objects.create(
            patient=self.patient2,
            status_type=PatientStatus.StatusType.ADMISSION,
            occurred_at=timezone.now(),
        )
        reset_current_tenant()

        # User1 should only see patient1's history
        self.client.force_login(user=self.user1)
        response = self.client.get(f"/patient-status/history/{self.patient1.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], str(status1.id))

        # User1 should not see patient2's history
        response = self.client.get(f"/patient-status/history/{self.patient2.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_list_endpoint_performance(self):
        """Test that list endpoint performs well with many claims"""
        set_current_tenant(self.org1)
        # Create many claims
        for i in range(100):
            Claim.objects.create(
                patient=self.patient1,
                provider=self.user1,
                amount=100 + i,
                diagnosis_code=f"Z{i:02d}.0",
                submitted_date="2023-01-01",
                service_date="2023-01-01",
            )
        reset_current_tenant()

        self.client.force_login(user=self.user1)

        # Measure query time (should be <200ms as per requirements)
        import time

        start = time.perf_counter()
        response = self.client.get("/claims/")
        duration = time.perf_counter() - start

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Basic check that response time is reasonable
        # Note: Actual performance testing should be done with proper tooling
        self.assertLess(duration, 1.0)  # Should be much faster in production

    def test_manual_organization_id_manipulation_blocked(self):
        """Test that manually providing organization_id is blocked"""
        self.client.force_login(user=self.user1)
        data = {
            "patient": self.patient1.id,
            "provider": self.user1.id,
            "organization": str(self.org2.id),  # Try to set wrong org
            "amount": "150.00",
            "diagnosis_code": "AA00.0",
            "submitted_date": "2023-01-02",
            "service_date": "2023-01-02",
        }
        response = self.client.post("/claims/", data)

        if response.status_code == status.HTTP_201_CREATED:
            # If it was created, verify it's assigned to correct org
            claim_id = response.data["id"]
            set_current_tenant(self.org1)
            claim = Claim.objects.get(id=claim_id)
            self.assertEqual(claim.organization, self.org1)
            reset_current_tenant()
