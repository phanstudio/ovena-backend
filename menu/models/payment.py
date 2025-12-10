from django.db import models
from django.conf import settings

class Payment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('abandoned', 'Abandoned'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    reference = models.CharField(max_length=100, unique=True, db_index=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    email = models.EmailField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    access_code = models.CharField(max_length=100, blank=True)
    authorization_url = models.URLField(blank=True)
    
    # Paystack response data
    paystack_response = models.JSONField(null=True, blank=True)
    
    # Metadata
    metadata = models.JSONField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.email} - {self.amount} - {self.status}"