import re

from django.core.exceptions import ValidationError


def validate_diagnosis_code(value):
    pattern = r"^[A-Z][0-9]{2}(\.[0-9]{1,4})?$"
    if not re.match(pattern, value):
        raise ValidationError(f"{value} is not a valid ICD-10 code")


def validate_procedure_code(value):
    pattern = r"^\d{5}$"
    if not re.match(pattern, value):
        raise ValidationError(f"{value} is not a valid CPT code")
