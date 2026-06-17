from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class Customer(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='customer_profile', null=True, blank=True)
    full_name = models.CharField(max_length=200)
    phone_number = models.CharField(max_length=15, unique=True)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField()
    estate = models.CharField(max_length=100)
    monthly_fee = models.DecimalField(max_digits=10, decimal_places=2, default=500.00)
    registration_date = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.full_name} - {self.estate}"
    
    @property
    def total_paid(self):
        return self.payment_set.filter(status='COMPLETED').aggregate(
            total=models.Sum('amount')
        )['total'] or 0
    
    @property
    def pending_bills(self):
        from django.db.models import Sum
        from datetime import datetime
        current_month = datetime.now().month
        current_year = datetime.now().year
        # Calculate months since registration
        months_registered = (current_year - self.registration_date.year) * 12 + (current_month - self.registration_date.month)
        total_expected = self.monthly_fee * max(months_registered, 1)
        return max(total_expected - self.total_paid, 0)
    
    class Meta:
        ordering = ['-registration_date']

class Payment(models.Model):
    PAYMENT_METHODS = (
        ('MPESA', 'M-Pesa'),
        ('CASH', 'Cash'),
    )
    
    STATUS = (
        ('PENDING', 'Pending'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    )
    
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHODS)
    transaction_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default='PENDING')
    payment_date = models.DateTimeField(default=timezone.now)
    receipt_number = models.CharField(max_length=50, unique=True, null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    
    def save(self, *args, **kwargs):
        if not self.receipt_number:
            import uuid
            self.receipt_number = f"RCP-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.customer.full_name} - {self.amount} - {self.payment_date}"