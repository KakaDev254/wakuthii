from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    path('mpesa-pay/', views.lipa_na_mpesa, name='mpesa_pay'),
    path('mpesa-callback/', views.mpesa_callback, name='mpesa_callback'),
]