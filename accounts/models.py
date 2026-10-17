from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    class Role(models.TextChoices):
        SYSTEM_ADMIN = "SYSTEM_ADMIN", "System Administrator"
        WAREHOUSE_OFFICER = "WAREHOUSE_OFFICER", "Warehouse Officer"
        ASC_OFFICER = "ASC_OFFICER", "ASC Officer"
        FARMER = "FARMER", "Farmer"
        AUDITOR = "AUDITOR", "Auditor"
        
    role = models.CharField (
        max_length = 30,
        choices = Role.choices,
        default = Role.FARMER
    )