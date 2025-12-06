import uuid

from django.contrib.auth.models import BaseUserManager
from django.db import models

from tenancy.utils import get_current_tenant


class Organization(models.Model):
    id = models.UUIDField(primary_key=True, editable=False, default=uuid.uuid4)
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"<Tenant {self.id}: {self.name}>"


class TenantManager(models.Manager):
    def get_queryset(self):
        queryset = super().get_queryset()
        tenant = get_current_tenant()
        if tenant is None:
            return queryset

        return queryset.filter(organization=tenant)


class TenantUserManager(BaseUserManager, TenantManager):
    def create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Email must be set")

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)


class TenantModel(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)

    objects = TenantManager()
    non_tenant_objects = models.Manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.organization_id:
            return super().save(*args, **kwargs)

        tenant = get_current_tenant()
        if tenant:
            self.organization = tenant
        return super().save(*args, **kwargs)
