from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import dateparse

from claims.models import Claim, Patient
from claims.tasks import (
    process_patient_admission,
    process_patient_discharge,
    process_treatment_initiated,
)
from tenancy.models import Organization
from tenancy.utils import reset_current_tenant, set_current_tenant

User = get_user_model()


class ProcessPatientAdmissionTaskTestCase(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Test Org")
        set_current_tenant(self.org)

        self.provider = User.objects.create_user(
            email="provider@example.com",
            password="pass",
            role=User.Role.PROVIDER,
        )
        self.patient = Patient.objects.create(
            first_name="Test",
            last_name="Patient",
            date_of_birth=dateparse.parse_date("1995-01-01"),
            email="patient@example.com",
            phone="555-0100",
        )

    def tearDown(self):
        reset_current_tenant()

    def test_process_admission_updates_submitted_claims(self):
        # Create multiple submitted claims
        claim1 = Claim.objects.create(
            patient=self.patient,
            provider=self.provider,
            amount=100.00,
            diagnosis_code="A00.0",
            submitted_date="2023-01-01",
            service_date="2023-01-01",
            status=Claim.Status.SUBMITTED,
        )
        claim2 = Claim.objects.create(
            patient=self.patient,
            provider=self.provider,
            amount=200.00,
            diagnosis_code="B00.0",
            submitted_date="2023-01-02",
            service_date="2023-01-02",
            status=Claim.Status.SUBMITTED,
        )

        # Create a claim with different status (should not be updated)
        claim3 = Claim.objects.create(
            patient=self.patient,
            provider=self.provider,
            amount=300.00,
            diagnosis_code="C00.0",
            submitted_date="2023-01-03",
            service_date="2023-01-03",
            status=Claim.Status.APPROVED,
        )

        reset_current_tenant()

        # Run the task
        process_patient_admission(
            patient_id=self.patient.id, organization_id=self.org.id
        )

        # Verify status updates
        claim1.refresh_from_db()
        claim2.refresh_from_db()
        claim3.refresh_from_db()

        self.assertEqual(claim1.status, Claim.Status.UNDER_REVIEW)
        self.assertEqual(claim2.status, Claim.Status.UNDER_REVIEW)
        self.assertEqual(claim3.status, Claim.Status.APPROVED)

    def test_process_admission_no_submitted_claims(self):
        # Create claims with non-submitted status
        _claim = Claim.objects.create(
            patient=self.patient,
            provider=self.provider,
            amount=100.00,
            diagnosis_code="D00.0",
            submitted_date="2023-01-01",
            service_date="2023-01-01",
            status=Claim.Status.APPROVED,
        )

        reset_current_tenant()

        # Run the task
        process_patient_admission(
            patient_id=self.patient.id, organization_id=self.org.id
        )

        # Verify no changes
        _claim.refresh_from_db()
        self.assertEqual(_claim.status, Claim.Status.APPROVED)

    def test_process_admission_different_organization(self):
        org2 = Organization.objects.create(name="Org 2")
        set_current_tenant(org2)
        patient2 = Patient.objects.create(
            first_name="P2",
            last_name="L2",
            date_of_birth=dateparse.parse_date("2000-01-01"),
            email="p2@org2.com",
            phone="222",
        )
        provider2 = User.objects.create_user(
            email="provider2@org2.com",
            password="pass",
            role=User.Role.PROVIDER,
        )
        claim2 = Claim.objects.create(
            patient=patient2,
            provider=provider2,
            amount=100.00,
            diagnosis_code="E00.0",
            submitted_date="2023-01-01",
            service_date="2023-01-01",
            status=Claim.Status.SUBMITTED,
        )
        reset_current_tenant()

        set_current_tenant(self.org)
        claim1 = Claim.objects.create(
            patient=self.patient,
            provider=self.provider,
            amount=100.00,
            diagnosis_code="F00.0",
            submitted_date="2023-01-01",
            service_date="2023-01-01",
            status=Claim.Status.SUBMITTED,
        )
        reset_current_tenant()

        # Run task for org1 patient
        process_patient_admission(
            patient_id=self.patient.id, organization_id=self.org.id
        )

        # Verify only org1 claim updated
        claim1.refresh_from_db()
        claim2.refresh_from_db()
        self.assertEqual(claim1.status, Claim.Status.UNDER_REVIEW)
        self.assertEqual(claim2.status, Claim.Status.SUBMITTED)

    @patch("claims.tasks.logger")
    def test_process_admission_logging(self, mock_logger):
        _claim = Claim.objects.create(
            patient=self.patient,
            provider=self.provider,
            amount=100.00,
            diagnosis_code="G00.0",
            submitted_date="2023-01-01",
            service_date="2023-01-01",
            status=Claim.Status.SUBMITTED,
        )
        reset_current_tenant()

        process_patient_admission(
            patient_id=self.patient.id, organization_id=self.org.id
        )

        # Verify logging was called
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0][0]
        self.assertIn("1 claims", call_args)
        self.assertIn("UNDER_REVIEW", call_args)
        self.assertIn(str(self.patient.id), call_args)


class ProcessPatientDischargeTaskTestCase(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Test Org")
        set_current_tenant(self.org)

        self.provider = User.objects.create_user(
            email="provider@example.com",
            password="pass",
            role=User.Role.PROVIDER,
        )
        self.patient = Patient.objects.create(
            first_name="Test",
            last_name="Patient",
            date_of_birth=dateparse.parse_date("1995-01-01"),
            email="patient@example.com",
            phone="555-0100",
        )

    def tearDown(self):
        reset_current_tenant()

    def test_process_discharge_updates_pending_claims(self):
        # Create submitted and under_review claims
        claim1 = Claim.objects.create(
            patient=self.patient,
            provider=self.provider,
            amount=100.00,
            diagnosis_code="H00.0",
            submitted_date="2023-01-01",
            service_date="2023-01-01",
            status=Claim.Status.SUBMITTED,
        )
        claim2 = Claim.objects.create(
            patient=self.patient,
            provider=self.provider,
            amount=200.00,
            diagnosis_code="I00.0",
            submitted_date="2023-01-02",
            service_date="2023-01-02",
            status=Claim.Status.UNDER_REVIEW,
        )

        # Create claim with different status (should not be updated)
        claim3 = Claim.objects.create(
            patient=self.patient,
            provider=self.provider,
            amount=300.00,
            diagnosis_code="J00.0",
            submitted_date="2023-01-03",
            service_date="2023-01-03",
            status=Claim.Status.PAID,
        )

        reset_current_tenant()

        # Run the task
        process_patient_discharge(
            patient_id=self.patient.id, organization_id=self.org.id
        )

        # Verify status updates
        claim1.refresh_from_db()
        claim2.refresh_from_db()
        claim3.refresh_from_db()

        self.assertEqual(claim1.status, Claim.Status.APPROVED)
        self.assertEqual(claim1.approval_reason, "Auto-finalize")
        self.assertEqual(claim2.status, Claim.Status.APPROVED)
        self.assertEqual(claim2.approval_reason, "Auto-finalize")
        self.assertEqual(claim3.status, Claim.Status.PAID)

    def test_process_discharge_no_pending_claims(self):
        # Create claim with non-pending status
        _claim = Claim.objects.create(
            patient=self.patient,
            provider=self.provider,
            amount=100.00,
            diagnosis_code="K00.0",
            submitted_date="2023-01-01",
            service_date="2023-01-01",
            status=Claim.Status.REJECTED,
        )

        reset_current_tenant()

        # Run the task
        process_patient_discharge(
            patient_id=self.patient.id, organization_id=self.org.id
        )

        # Verify no changes
        _claim.refresh_from_db()
        self.assertEqual(_claim.status, Claim.Status.REJECTED)
        self.assertIsNone(_claim.approval_reason)

    def test_process_discharge_different_organization(self):
        org2 = Organization.objects.create(name="Org 2")
        set_current_tenant(org2)
        patient2 = Patient.objects.create(
            first_name="P2",
            last_name="L2",
            date_of_birth=dateparse.parse_date("2000-01-01"),
            email="p2@org2.com",
            phone="222",
        )
        provider2 = User.objects.create_user(
            email="provider2@org2.com",
            password="pass",
            role=User.Role.PROVIDER,
        )
        claim2 = Claim.objects.create(
            patient=patient2,
            provider=provider2,
            amount=100.00,
            diagnosis_code="L00.0",
            submitted_date="2023-01-01",
            service_date="2023-01-01",
            status=Claim.Status.SUBMITTED,
        )
        reset_current_tenant()

        set_current_tenant(self.org)
        claim1 = Claim.objects.create(
            patient=self.patient,
            provider=self.provider,
            amount=100.00,
            diagnosis_code="M00.0",
            submitted_date="2023-01-01",
            service_date="2023-01-01",
            status=Claim.Status.SUBMITTED,
        )
        reset_current_tenant()

        # Run task for org1 patient
        process_patient_discharge(
            patient_id=self.patient.id, organization_id=self.org.id
        )

        # Verify only org1 claim updated
        claim1.refresh_from_db()
        claim2.refresh_from_db()
        self.assertEqual(claim1.status, Claim.Status.APPROVED)
        self.assertEqual(claim2.status, Claim.Status.SUBMITTED)

    @patch("claims.tasks.logger")
    def test_process_discharge_logging(self, mock_logger):
        _claim1 = Claim.objects.create(
            patient=self.patient,
            provider=self.provider,
            amount=100.00,
            diagnosis_code="N00.0",
            submitted_date="2023-01-01",
            service_date="2023-01-01",
            status=Claim.Status.SUBMITTED,
        )
        _claim2 = Claim.objects.create(
            patient=self.patient,
            provider=self.provider,
            amount=200.00,
            diagnosis_code="O00.0",
            submitted_date="2023-01-02",
            service_date="2023-01-02",
            status=Claim.Status.UNDER_REVIEW,
        )
        reset_current_tenant()

        process_patient_discharge(
            patient_id=self.patient.id, organization_id=self.org.id
        )

        # Verify logging was called
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0][0]
        self.assertIn("2 claims", call_args)
        self.assertIn("APPROVED", call_args)
        self.assertIn(str(self.patient.id), call_args)


class ProcessTreatmentInitiatedTaskTestCase(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Test Org")
        set_current_tenant(self.org)

        self.provider = User.objects.create_user(
            email="provider@example.com",
            password="pass",
            role=User.Role.PROVIDER,
        )
        self.patient = Patient.objects.create(
            first_name="Test",
            last_name="Patient",
            date_of_birth=dateparse.parse_date("1995-01-01"),
            email="patient@example.com",
            phone="555-0100",
        )

    def tearDown(self):
        reset_current_tenant()

    def test_process_treatment_updates_submitted_claims(self):
        # Create submitted claims
        claim1 = Claim.objects.create(
            patient=self.patient,
            provider=self.provider,
            amount=100.00,
            diagnosis_code="P00.0",
            submitted_date="2023-01-01",
            service_date="2023-01-01",
            status=Claim.Status.SUBMITTED,
        )
        claim2 = Claim.objects.create(
            patient=self.patient,
            provider=self.provider,
            amount=200.00,
            diagnosis_code="Q00.0",
            submitted_date="2023-01-02",
            service_date="2023-01-02",
            status=Claim.Status.SUBMITTED,
        )

        # Create claim with different status
        claim3 = Claim.objects.create(
            patient=self.patient,
            provider=self.provider,
            amount=300.00,
            diagnosis_code="R00.0",
            submitted_date="2023-01-03",
            service_date="2023-01-03",
            status=Claim.Status.APPROVED,
        )

        reset_current_tenant()

        # Run the task
        process_treatment_initiated(
            patient_id=self.patient.id,
            organization_id=self.org.id,
            treatment_type="chemotherapy",
        )

        # Verify status updates
        claim1.refresh_from_db()
        claim2.refresh_from_db()
        claim3.refresh_from_db()

        self.assertEqual(claim1.status, Claim.Status.UNDER_REVIEW)
        self.assertEqual(claim2.status, Claim.Status.UNDER_REVIEW)
        self.assertEqual(claim3.status, Claim.Status.APPROVED)

    def test_process_treatment_no_submitted_claims(self):
        # Create claim with non-submitted status
        _claim = Claim.objects.create(
            patient=self.patient,
            provider=self.provider,
            amount=100.00,
            diagnosis_code="S00.0",
            submitted_date="2023-01-01",
            service_date="2023-01-01",
            status=Claim.Status.UNDER_REVIEW,
        )

        reset_current_tenant()

        # Run the task
        process_treatment_initiated(
            patient_id=self.patient.id,
            organization_id=self.org.id,
            treatment_type="surgery",
        )

        # Verify no changes
        _claim.refresh_from_db()
        self.assertEqual(_claim.status, Claim.Status.UNDER_REVIEW)

    def test_process_treatment_different_organization(self):
        org2 = Organization.objects.create(name="Org 2")
        set_current_tenant(org2)
        patient2 = Patient.objects.create(
            first_name="P2",
            last_name="L2",
            date_of_birth=dateparse.parse_date("2000-01-01"),
            email="p2@org2.com",
            phone="222",
        )
        provider2 = User.objects.create_user(
            email="provider2@org2.com",
            password="pass",
            role=User.Role.PROVIDER,
        )
        claim2 = Claim.objects.create(
            patient=patient2,
            provider=provider2,
            amount=100.00,
            diagnosis_code="T00.0",
            submitted_date="2023-01-01",
            service_date="2023-01-01",
            status=Claim.Status.SUBMITTED,
        )
        reset_current_tenant()

        set_current_tenant(self.org)
        claim1 = Claim.objects.create(
            patient=self.patient,
            provider=self.provider,
            amount=100.00,
            diagnosis_code="U00.0",
            submitted_date="2023-01-01",
            service_date="2023-01-01",
            status=Claim.Status.SUBMITTED,
        )
        reset_current_tenant()

        # Run task for org1 patient
        process_treatment_initiated(
            patient_id=self.patient.id,
            organization_id=self.org.id,
            treatment_type="radiation",
        )

        # Verify only org1 claim updated
        claim1.refresh_from_db()
        claim2.refresh_from_db()
        self.assertEqual(claim1.status, Claim.Status.UNDER_REVIEW)
        self.assertEqual(claim2.status, Claim.Status.SUBMITTED)

    @patch("claims.tasks.logger")
    def test_process_treatment_logging(self, mock_logger):
        _claim = Claim.objects.create(
            patient=self.patient,
            provider=self.provider,
            amount=100.00,
            diagnosis_code="V00.0",
            submitted_date="2023-01-01",
            service_date="2023-01-01",
            status=Claim.Status.SUBMITTED,
        )
        reset_current_tenant()

        treatment_type = "physical therapy"
        process_treatment_initiated(
            patient_id=self.patient.id,
            organization_id=self.org.id,
            treatment_type=treatment_type,
        )

        # Verify logging was called
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0][0]
        self.assertIn(treatment_type, call_args)
        self.assertIn("1 claims", call_args)
        self.assertIn("UNDER_REVIEW", call_args)
        self.assertIn(str(self.patient.id), call_args)

    def test_process_treatment_with_various_treatment_types(self):
        claim1 = Claim.objects.create(
            patient=self.patient,
            provider=self.provider,
            amount=100.00,
            diagnosis_code="W00.0",
            submitted_date="2023-01-01",
            service_date="2023-01-01",
            status=Claim.Status.SUBMITTED,
        )
        reset_current_tenant()

        # Test with different treatment types
        for treatment_type in ["surgery", "medication", "therapy", "diagnostic"]:
            claim1.status = Claim.Status.SUBMITTED
            claim1.save()

            process_treatment_initiated(
                patient_id=self.patient.id,
                organization_id=self.org.id,
                treatment_type=treatment_type,
            )

            claim1.refresh_from_db()
            self.assertEqual(claim1.status, Claim.Status.UNDER_REVIEW)


class TaskTransactionTestCase(TestCase):
    """Test that tasks use transactions properly"""

    def setUp(self):
        self.org = Organization.objects.create(name="Test Org")
        set_current_tenant(self.org)

        self.provider = User.objects.create_user(
            email="provider@example.com",
            password="pass",
            role=User.Role.PROVIDER,
        )
        self.patient = Patient.objects.create(
            first_name="Test",
            last_name="Patient",
            date_of_birth=dateparse.parse_date("1995-01-01"),
            email="patient@example.com",
            phone="555-0100",
        )

    def tearDown(self):
        reset_current_tenant()

    def test_admission_task_atomicity(self):
        # Create claims
        claims = []
        for i in range(3):
            claim = Claim.objects.create(
                patient=self.patient,
                provider=self.provider,
                amount=100.00 * (i + 1),
                diagnosis_code=f"X{i:02d}.0",
                submitted_date="2023-01-01",
                service_date="2023-01-01",
                status=Claim.Status.SUBMITTED,
            )
            claims.append(claim)

        reset_current_tenant()

        # Run task
        process_patient_admission(
            patient_id=self.patient.id, organization_id=self.org.id
        )

        # All should be updated or none
        statuses = [
            c.status for c in Claim.objects.filter(id__in=[c.id for c in claims])
        ]
        self.assertTrue(
            all(s == Claim.Status.UNDER_REVIEW for s in statuses)
            or all(s == Claim.Status.SUBMITTED for s in statuses)
        )
