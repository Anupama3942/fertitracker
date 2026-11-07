from django.db import models

# Create your models here.

from django.contrib.auth.models import AbstractUser
from core.models import ASCCentre

class User(AbstractUser):
    class RoleChoices(models.TextChoices):
        ADMIN               = 'ADMIN', 'System Administor'
        WAREHOUSE_OFFICER   = 'WAREHOUSE_OFFICER', 'Warehouse Officer'
        ASC_OFFICER        = 'ASC_OFFICER', 'ASC Officer'
        FARMER             = 'FARMER', 'Farmer'
        AUDITOR = 'AUDIOR', 'Auditor' 
        
    role = models.CharField(
        max_length=30,
        choices=RoleChoices.choices,
        default=RoleChoices.FARMER
    )
    
    asc_centre = models.ForeignKey(
        ASCCentre,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='officers'
    )
    
    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"