from django.db import models

from tenancy.utils import get_current_tenant


class TenantManager(models.Manager):
    def get_queryset(self):
        queryset = super().get_queryset()
        tenant = get_current_tenant()
        if tenant:
            return queryset.filter(organization=tenant)
        return queryset


class TenantAwareModel(models.Model):
    organization = models.ForeignKey("claims.Organization", on_delete=models.CASCADE)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self.organization_id:
            tenant = get_current_tenant()
            if tenant:
                self.organization = tenant
        super().save(*args, **kwargs)
