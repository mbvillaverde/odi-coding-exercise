import random

from django.core.management.base import BaseCommand
from django.utils import timezone, dateparse

from claims.models import Patient, User, Claim
from tenancy.models import Organization


class Command(BaseCommand):
    help = "Populate Tenant Data for Demo Purposes"

    def handle(self, *args, **kwargs):
        # Create Organizations
        for i in range(1, 4):
            Organization.objects.create(name=f"Organization {i}")

        user_patients = []

        # Create Users
        organizations = Organization.objects.all().order_by("id")
        for i, organization in enumerate(organizations, start=1):
            User.objects.create_user(
                email=f"admin@org{i}.com",
                password=f"admin{i}password",
                organization=organization,
                first_name=f"Org {i} Admin",
                last_name="User",
                role=User.Role.ADMIN,
            )

            User.objects.create_user(
                email=f"claims_processor@org{i}.com",
                password=f"claims_processor{i}password",
                organization=organization,
                first_name=f"Org {i} Claims Processor",
                last_name="User",
                role=User.Role.CLAIMS_PROCESSOR,
            )

            User.objects.create_user(
                email=f"provider@org{i}.com",
                password=f"provider{i}password",
                organization=organization,
                first_name=f"Org {i} Claims Processor",
                last_name="User",
                role=User.Role.PROVIDER,
            )

            user_patient = User.objects.create_user(
                email=f"patient@org{i}.com",
                password=f"patient{i}password",
                organization=organization,
                first_name=f"Org {i} Patient",
                last_name="User",
                role=User.Role.PATIENT,
            )
            user_patients.append(user_patient)

        # Create Patient Data
        patients = []
        for user_patient in user_patients:
            year_of_birth = random.randint(1990, 1996)
            patient = Patient.objects.create(
                organization=user_patient.organization,
                first_name=user_patient.first_name,
                last_name=user_patient.last_name,
                date_of_birth=dateparse.parse_date(f"{year_of_birth}-4-23"),
                email=user_patient.email,
                phone="111-1111",
            )
            patients.append(patient)

        # Create Claim for Each Patient
        for patient in patients:
            Claim.objects.create(
                organization=patient.organization,
                patient=patient,
                provider=User.objects.filter(
                    role=User.Role.PROVIDER, organization=patient.organization
                ).first(),
                assigned_processor=User.objects.filter(
                    role=User.Role.CLAIMS_PROCESSOR, organization=patient.organization
                ).first(),
                diagnosis_code="A00",
                procedure_code="01999",
                amount=1_000_000,
                submitted_date=timezone.now(),
                service_date=timezone.now(),
            )

        print("Populating data finished!")
