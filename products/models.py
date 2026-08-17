from django.db import models


class Product(models.Model):
    description = models.CharField(max_length=255)
    stock = models.DecimalField(max_digits=12, decimal_places=3)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return self.description