from django.db import models

# Create your models here.

class Warehouse(models.Model):
    name        = models.CharField(max_length=150)
    location    = models.CharField(max_length=255)
    
    def __str__(self):
        return f"{self.name} ({self.location})"
    
class ASCCentre(models.Model):
    name = models.CharField(max_length=150)
    district = models.CharField(max_length=100)
    address = models.CharField(max_length=255)
    
    def __str__(self):
        return f"{self.name} - {self.district}"
        
class Season(models.Model):
    class StstusChoices(models.TextChoices):
        UCOMING = 'UPCOMING', 'Upcoming'
        ACTIVE  = 'ACTIVE', 'Active'
        CLOSED  = 'CLOSED', 'Closed'
        
    name        = models.CharField(max_length=100)
    start_date  = models.DateField()
    end_date    = models.DateField()
    status      = models.CharField(
        max_length=30,
        choices=StstusChoices.choices,
        default=StstusChoices.ACTIVE
    ) 
    
    def __str__(self):
        return f"{self.name} ({self.status})"
    
class FertilizerProduct(models.Model):
    name  = models.CharField(max_length=150)
    bag_weight_kg = models.DecimalField(max_digits=8, decimal_places=2)
    
    def __str__(self):
        return f"{self.name} ({self.bag_weight_kg} kg)"