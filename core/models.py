from django.db import models


class Warehouse(models.Model):
    name = models.CharField(max_length=150)
    location = models.CharField(max_length=255)

    def __str__(self):
        return self.name


class ASCCentre(models.Model):
    name = models.CharField(max_length=150)
    district = models.CharField(max_length=100)
    address = models.CharField(max_length=255)

    def __str__(self):
        return self.name


class Season(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"
        CLOSED = "CLOSED", "Closed"

    name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )

    def __str__(self):
        return self.name


class FertilizerProduct(models.Model):
    name = models.CharField(
        max_length=150,
        unique=True,
    )

    bag_weight_kg = models.DecimalField(
        max_digits=8,
        decimal_places=2,
    )

    def __str__(self):
        return self.name