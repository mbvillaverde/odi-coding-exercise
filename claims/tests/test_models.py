from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import dateparse, timezone

from claims.models import Claim, Patient, PatientStatus
from tenancy.models import Organization
from tenancy.utils import reset_current_tenant, set_current_tenant

User = get_user_model()


class UserModelTestCase(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Test Org")
        set_current_tenant(self.org)

    def tearDown(self):
        reset_current_tenant()

    def test_create_user(self):
        user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
            role=User.Role.ADMIN,
        )
        self.assertEqual(user.email, "test@example.com")
        self.assertEqual(user.role, User.Role.ADMIN)
        self.assertTrue(user.check_password("testpass123"))
        self.assertEqual(user.organization, self.org)
        self.assertTrue(user.is_active)

    def test_user_str_representation(self):
        user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
        )
        self.assertIn(str(user.id), str(user))
        self.assertIn("test@example.com", str(user))

    def test_user_roles(self):
        admin = User.objects.create_user(
            email="admin@example.com",
            password="pass",
            role=User.Role.ADMIN,
        )
        processor = User.objects.create_user(
            email="processor@example.com",
            password="pass",
            role=User.Role.CLAIMS_PROCESSOR,
        )
        provider = User.objects.create_user(
            email="provider@example.com",
            password="pass",
            role=User.Role.PROVIDER,
        )
        patient = User.objects.create_user(
            email="patient@example.com",
            password="pass",
            role=User.Role.PATIENT,
        )

        self.assertEqual(admin.role, User.Role.ADMIN)
        self.assertEqual(processor.role, User.Role.CLAIMS_PROCESSOR)
        self.assertEqual(provider.role, User.Role.PROVIDER)
        self.assertEqual(patient.role, User.Role.PATIENT)

    def test_user_tenant_isolation(self):
        org2 = Organization.objects.create(name="Org 2")

        user1 = User.objects.create_user(
            email="user1@org1.com",
            password="pass",
            organization=self.org,
        )

        set_current_tenant(org2)
        user2 = User.objects.create_user(
            email="user2@org2.com",
            password="pass",
            organization=org2,
        )

        # Query from org2 context
        users = User.objects.all()
        self.assertEqual(users.count(), 1)
        self.assertEqual(users.first().id, user2.id)

        set_current_tenant(self.org)
        users = User.objects.all()
        self.assertEqual(users.count(), 1)
        self.assertEqual(users.first().id, user1.id)

    def test_user_without_tenant_context(self):
        reset_current_tenant()
        user = User.objects.create_user(
            email="nocontext@example.com",
            password="pass",
            organization=self.org,
        )
        self.assertEqual(
            user.organization,
            self.org,
            "User should still be created with explicit organization",
        )


class PatientModelTestCase(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Test Org")
        set_current_tenant(self.org)

    def tearDown(self):
        reset_current_tenant()

    def test_create_patient(self):
        patient = Patient.objects.create(
            first_name="John",
            last_name="Doe",
            date_of_birth=dateparse.parse_date("1990-01-01"),
            email="john.doe@example.com",
            phone="1234567890",
        )
        self.assertEqual(patient.first_name, "John")
        self.assertEqual(patient.last_name, "Doe")
        self.assertEqual(patient.email, "john.doe@example.com")
        self.assertEqual(patient.organization, self.org)

    def test_patient_str_representation(self):
        patient = Patient.objects.create(
            first_name="Jane",
            last_name="Smith",
            date_of_birth=dateparse.parse_date("1985-05-15"),
            email="jane.smith@example.com",
            phone="9876543210",
        )
        self.assertIn(str(patient.id), str(patient))
        self.assertIn("jane.smith@example.com", str(patient))

    def test_patient_tenant_isolation(self):
        org2 = Organization.objects.create(name="Org 2")

        patient1 = Patient.objects.create(
            first_name="P1",
            last_name="L1",
            date_of_birth=dateparse.parse_date("2000-01-01"),
            email="p1@org1.com",
            phone="111",
        )

        set_current_tenant(org2)
        patient2 = Patient.objects.create(
            first_name="P2",
            last_name="L2",
            date_of_birth=dateparse.parse_date("2000-01-01"),
            email="p2@org2.com",
            phone="222",
        )

        patients = Patient.objects.all()
        self.assertEqual(patients.count(), 1)
        self.assertEqual(patients.first().id, patient2.id)

        set_current_tenant(self.org)
        patients = Patient.objects.all()
        self.assertEqual(patients.count(), 1)
        self.assertEqual(patients.first().id, patient1.id)


class ClaimModelTestCase(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Test Org")
        set_current_tenant(self.org)

        self.provider = User.objects.create_user(
            email="provider@example.com",
            password="pass",
            role=User.Role.PROVIDER,
        )
        self.processor = User.objects.create_user(
            email="processor@example.com",
            password="pass",
            role=User.Role.CLAIMS_PROCESSOR,
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

    def test_create_claim(self):
        claim = Claim.objects.create(
            patient=self.patient,
            provider=self.provider,
            amount=150.00,
            diagnosis_code="A00.1",
            procedure_code="12345",
            submitted_date="2023-01-15",
            service_date="2023-01-10",
        )
        self.assertEqual(claim.patient, self.patient)
        self.assertEqual(claim.provider, self.provider)
        self.assertEqual(claim.amount, 150.00)
        self.assertEqual(claim.status, Claim.Status.SUBMITTED)
        self.assertEqual(claim.organization, self.org)

    def test_claim_with_assigned_processor(self):
        claim = Claim.objects.create(
            patient=self.patient,
            provider=self.provider,
            assigned_processor=self.processor,
            amount=200.00,
            diagnosis_code="B00.1",
            submitted_date="2023-02-01",
            service_date="2023-01-28",
        )
        self.assertEqual(claim.assigned_processor, self.processor)

    def test_claim_status_choices(self):
        claim = Claim.objects.create(
            patient=self.patient,
            provider=self.provider,
            amount=100.00,
            diagnosis_code="C00.1",
            submitted_date="2023-01-01",
            service_date="2023-01-01",
        )

        claim.status = Claim.Status.UNDER_REVIEW
        claim.save()
        self.assertEqual(claim.status, Claim.Status.UNDER_REVIEW)

        claim.status = Claim.Status.APPROVED
        claim.approval_reason = "All documentation verified"
        claim.save()
        self.assertEqual(claim.status, Claim.Status.APPROVED)
        self.assertIsNotNone(claim.approval_reason)

        claim.status = Claim.Status.PAID
        claim.save()
        self.assertEqual(claim.status, Claim.Status.PAID)

    def test_claim_rejection(self):
        claim = Claim.objects.create(
            patient=self.patient,
            provider=self.provider,
            amount=100.00,
            diagnosis_code="D00.1",
            submitted_date="2023-01-01",
            service_date="2023-01-01",
        )
        claim.status = Claim.Status.REJECTED
        claim.rejection_reason = "Insufficient documentation"
        claim.save()

        self.assertEqual(claim.status, Claim.Status.REJECTED)
        self.assertEqual(claim.rejection_reason, "Insufficient documentation")

    def test_claim_str_representation(self):
        claim = Claim.objects.create(
            patient=self.patient,
            provider=self.provider,
            amount=100.00,
            diagnosis_code="E00.1",
            procedure_code="67890",
            submitted_date="2023-01-01",
            service_date="2023-01-01",
        )
        str_repr = str(claim)
        self.assertIn(str(claim.id), str_repr)
        self.assertIn("E00.1", str_repr)
        self.assertIn("67890", str_repr)
        self.assertIn("submitted", str_repr)

    def test_claim_tenant_isolation(self):
        org2 = Organization.objects.create(name="Org 2")

        claim1 = Claim.objects.create(
            patient=self.patient,
            provider=self.provider,
            amount=100.00,
            diagnosis_code="F00.1",
            submitted_date="2023-01-01",
            service_date="2023-01-01",
        )

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
            amount=200.00,
            diagnosis_code="G00.1",
            submitted_date="2023-01-01",
            service_date="2023-01-01",
        )

        claims = Claim.objects.all()
        self.assertEqual(claims.count(), 1)
        self.assertEqual(claims.first().id, claim2.id)

        set_current_tenant(self.org)
        claims = Claim.objects.all()
        self.assertEqual(claims.count(), 1)
        self.assertEqual(claims.first().id, claim1.id)

    def test_claim_timestamps(self):
        claim = Claim.objects.create(
            patient=self.patient,
            provider=self.provider,
            amount=100.00,
            diagnosis_code="H00.1",
            submitted_date="2023-01-01",
            service_date="2023-01-01",
        )
        self.assertIsNotNone(claim.created_at)
        self.assertIsNotNone(claim.updated_at)

        created_at = claim.created_at
        claim.status = Claim.Status.UNDER_REVIEW
        claim.save()
        claim.refresh_from_db()

        self.assertEqual(claim.created_at, created_at)
        self.assertGreater(claim.updated_at, created_at)


class PatientStatusModelTestCase(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Test Org")
        set_current_tenant(self.org)

        self.patient = Patient.objects.create(
            first_name="Test",
            last_name="Patient",
            date_of_birth=dateparse.parse_date("1995-01-01"),
            email="patient@example.com",
            phone="555-0100",
        )

    def tearDown(self):
        reset_current_tenant()

    def test_create_admission_status(self):
        status = PatientStatus.objects.create(
            patient=self.patient,
            status_type=PatientStatus.StatusType.ADMISSION,
            facility_name="Central Hospital",
            details={"room": "101", "wing": "A"},
            occurred_at=timezone.now(),
        )
        self.assertEqual(status.patient, self.patient)
        self.assertEqual(status.status_type, PatientStatus.StatusType.ADMISSION)
        self.assertEqual(status.facility_name, "Central Hospital")
        self.assertEqual(status.details["room"], "101")
        self.assertEqual(status.organization, self.org)

    def test_create_discharge_status(self):
        status = PatientStatus.objects.create(
            patient=self.patient,
            status_type=PatientStatus.StatusType.DISCHARGE,
            facility_name="Central Hospital",
            details={"discharge_type": "normal"},
            occurred_at=timezone.now(),
        )
        self.assertEqual(status.status_type, PatientStatus.StatusType.DISCHARGE)

    def test_create_treatment_status(self):
        status = PatientStatus.objects.create(
            patient=self.patient,
            status_type=PatientStatus.StatusType.TREATMENT_INITIATED,
            details={"treatment_type": "chemotherapy", "doctor": "Dr. Smith"},
            occurred_at=timezone.now(),
        )
        self.assertEqual(
            status.status_type, PatientStatus.StatusType.TREATMENT_INITIATED
        )
        self.assertEqual(status.details["treatment_type"], "chemotherapy")

    def test_patient_status_str_representation(self):
        status = PatientStatus.objects.create(
            patient=self.patient,
            status_type=PatientStatus.StatusType.ADMISSION,
            occurred_at=timezone.now(),
        )
        str_repr = str(status)
        self.assertIn(str(status.id), str_repr)
        self.assertIn("admission", str_repr.lower())

    def test_patient_status_tenant_isolation(self):
        org2 = Organization.objects.create(name="Org 2")

        status1 = PatientStatus.objects.create(
            patient=self.patient,
            status_type=PatientStatus.StatusType.ADMISSION,
            occurred_at=timezone.now(),
        )

        set_current_tenant(org2)
        patient2 = Patient.objects.create(
            first_name="P2",
            last_name="L2",
            date_of_birth=dateparse.parse_date("2000-01-01"),
            email="p2@org2.com",
            phone="222",
        )
        status2 = PatientStatus.objects.create(
            patient=patient2,
            status_type=PatientStatus.StatusType.DISCHARGE,
            occurred_at=timezone.now(),
        )

        statuses = PatientStatus.objects.all()
        self.assertEqual(statuses.count(), 1)
        self.assertEqual(statuses.first().id, status2.id)

        set_current_tenant(self.org)
        statuses = PatientStatus.objects.all()
        self.assertEqual(statuses.count(), 1)
        self.assertEqual(statuses.first().id, status1.id)

    def test_patient_status_default_details(self):
        status = PatientStatus.objects.create(
            patient=self.patient,
            status_type=PatientStatus.StatusType.ADMISSION,
            occurred_at=timezone.now(),
        )
        self.assertIsInstance(status.details, dict)
        self.assertEqual(status.details, {})

    def test_patient_status_timestamps(self):
        occurred_time = timezone.now()
        status = PatientStatus.objects.create(
            patient=self.patient,
            status_type=PatientStatus.StatusType.ADMISSION,
            occurred_at=occurred_time,
        )
        self.assertEqual(status.occurred_at, occurred_time)
        self.assertIsNotNone(status.created_at)
