from rest_framework import permissions

from claims.models import User


class CanManageClaim(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        user = request.user
        match user.role:
            # Grant Full Access
            case User.Role.ADMIN:
                return True

            # Grant Access to Assigned Claim
            case User.Role.CLAIMS_PROCESSOR:
                return obj.assigned_processor == user

            # Grant Read Access to Claim it provides
            case User.Role.PROVIDER:
                return (
                    obj.provider == user and request.method in permissions.SAFE_METHODS
                )

            # Grant Read Access to Own Claim
            case User.Role.PATIENT:
                return (
                    obj.patient.email == user.email
                    and request.method in permissions.SAFE_METHODS
                )

            case _:
                return False
