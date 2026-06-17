from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.core.paginator import Paginator
from django.http import JsonResponse
from .models import Customer, Payment
from .forms import CustomerForm, CashPaymentForm, CustomerImportForm
import pandas as pd
import io
import openpyxl

def is_admin(user):
    return user.is_superuser or user.is_staff

def home(request):
    return render(request, 'core/home.html')

def about(request):
    return render(request, 'core/about.html')

def services(request):
    return render(request, 'core/services.html')

def contact(request):
    return render(request, 'core/contact.html')

@user_passes_test(is_admin)
def admin_dashboard(request):
    # Get all customers
    customers = Customer.objects.filter(is_active=True)
    
    # Calculate totals
    total_customers = customers.count()
    total_expected_monthly = customers.aggregate(total=Sum('monthly_fee'))['total'] or 0
    
    # Get current month payments
    current_month = timezone.now().month
    current_year = timezone.now().year
    
    monthly_payments = Payment.objects.filter(
        status='COMPLETED',
        payment_date__month=current_month,
        payment_date__year=current_year
    )
    
    amounts_paid_month = monthly_payments.aggregate(total=Sum('amount'))['total'] or 0
    
    # Get all pending bills for customers
    pending_total = 0
    customer_data = []
    
    for customer in customers:
        pending = customer.pending_bills
        pending_total += pending
        customer_data.append({
            'customer': customer,
            'total_paid': customer.total_paid,
            'pending_bills': pending,
            'monthly_fee': customer.monthly_fee,
        })
    
    # Recent payments
    recent_payments = Payment.objects.filter(status='COMPLETED').order_by('-payment_date')[:10]
    
    # Cash payment form
    if request.method == 'POST' and 'cash_payment' in request.POST:
        form = CashPaymentForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.payment_method = 'CASH'
            payment.status = 'COMPLETED'
            payment.payment_date = timezone.now()
            payment.save()
            messages.success(request, f'Payment of KES {payment.amount} recorded successfully!')
            return redirect('core:admin_dashboard')
    else:
        form = CashPaymentForm()
    
    context = {
        'total_customers': total_customers,
        'total_expected_monthly': total_expected_monthly,
        'amounts_paid_month': amounts_paid_month,
        'pending_total': pending_total,
        'customer_data': customer_data,
        'recent_payments': recent_payments,
        'form': form,
    }
    
    return render(request, 'core/admin_dashboard.html', context)

@user_passes_test(is_admin)
def customer_list(request):
    # Get search query
    search_query = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')
    
    customers = Customer.objects.all()
    
    # Search functionality
    if search_query:
        customers = customers.filter(
            Q(full_name__icontains=search_query) |
            Q(phone_number__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(estate__icontains=search_query) |
            Q(address__icontains=search_query)
        )
    
    # Filter by status
    if status_filter == 'active':
        customers = customers.filter(is_active=True)
    elif status_filter == 'inactive':
        customers = customers.filter(is_active=False)
    elif status_filter == 'pending':
        # Customers with pending bills
        pending_customers = []
        for customer in customers:
            if customer.pending_bills > 0:
                pending_customers.append(customer.id)
        customers = customers.filter(id__in=pending_customers)
    
    # Pagination
    paginator = Paginator(customers, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'search_query': search_query,
        'status_filter': status_filter,
        'total_customers': Customer.objects.count(),
    }
    
    return render(request, 'core/customer_list.html', context)

@user_passes_test(is_admin)
def customer_add(request):
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            customer = form.save()
            messages.success(request, f'Customer {customer.full_name} added successfully!')
            return redirect('core:customer_list')
    else:
        form = CustomerForm()
    
    return render(request, 'core/customer_form.html', {'form': form, 'title': 'Add Customer'})

@user_passes_test(is_admin)
def customer_edit(request, customer_id):
    customer = get_object_or_404(Customer, id=customer_id)
    
    if request.method == 'POST':
        form = CustomerForm(request.POST, instance=customer)
        if form.is_valid():
            form.save()
            messages.success(request, f'Customer {customer.full_name} updated successfully!')
            return redirect('core:customer_list')
    else:
        form = CustomerForm(instance=customer)
    
    return render(request, 'core/customer_form.html', {'form': form, 'title': 'Edit Customer', 'customer': customer})

@user_passes_test(is_admin)
def customer_delete(request, customer_id):
    customer = get_object_or_404(Customer, id=customer_id)
    
    if request.method == 'POST':
        customer_name = customer.full_name
        customer.delete()
        messages.success(request, f'Customer {customer_name} deleted successfully!')
        return redirect('core:customer_list')
    
    return render(request, 'core/customer_confirm_delete.html', {'customer': customer})

@user_passes_test(is_admin)
def customer_import(request):
    if request.method == 'POST':
        form = CustomerImportForm(request.POST, request.FILES)
        if form.is_valid():
            excel_file = request.FILES['excel_file']
            try:
                # Read Excel file - ensure phone numbers are read as strings
                df = pd.read_excel(excel_file, dtype={'phone_number': str})
                
                required_columns = ['full_name', 'phone_number', 'estate']
                
                missing_columns = [col for col in required_columns if col not in df.columns]
                if missing_columns:
                    messages.error(request, f'Missing columns: {", ".join(missing_columns)}')
                    return redirect('core:customer_import')
                
                imported_count = 0
                skipped_count = 0
                errors = []
                
                for index, row in df.iterrows():
                    try:
                        # Get full_name
                        full_name = str(row.get('full_name', '')).strip()
                        if not full_name:
                            skipped_count += 1
                            errors.append(f"Row {index+2}: Missing full_name")
                            continue
                        
                        # Handle phone number properly - convert to string and clean
                        phone_raw = str(row.get('phone_number', '')).strip()
                        # Remove any non-digit characters
                        phone = ''.join(filter(str.isdigit, phone_raw))
                        
                        # Check if phone number is valid
                        if len(phone) < 10:
                            skipped_count += 1
                            errors.append(f"Row {index+2}: Invalid phone number {phone_raw} - must be at least 10 digits")
                            continue
                        
                        # Format phone number - ensure it starts with 0 for Kenya
                        if len(phone) == 12 and phone.startswith('254'):
                            phone = '0' + phone[3:]
                        elif len(phone) == 10 and phone.startswith('7'):
                            phone = '0' + phone
                        elif len(phone) == 9 and phone.startswith('7'):
                            phone = '0' + phone
                        elif len(phone) == 10 and phone.startswith('0'):
                            pass  # Already in correct format
                        elif len(phone) == 11 and phone.startswith('254'):
                            phone = '0' + phone[3:]
                        else:
                            # Try to fix common formats
                            if len(phone) >= 10:
                                phone = phone[-10:]  # Take last 10 digits
                                if phone.startswith('7'):
                                    phone = '0' + phone
                        
                        # Final validation - must start with 0 and be 10 digits
                        if len(phone) != 10 or not phone.startswith('0'):
                            skipped_count += 1
                            errors.append(f"Row {index+2}: Invalid phone number format {phone_raw} - expected 10 digits starting with 0")
                            continue
                        
                        # Check if customer already exists
                        existing = Customer.objects.filter(phone_number=phone).first()
                        if existing:
                            skipped_count += 1
                            errors.append(f"Row {index+2}: Customer with phone {phone} already exists ({existing.full_name})")
                            continue
                        
                        # Get optional fields
                        email = str(row.get('email', '')).strip() if pd.notna(row.get('email')) else ''
                        address = str(row.get('address', '')).strip() if pd.notna(row.get('address')) else ''
                        estate = str(row.get('estate', '')).strip()
                        
                        if not estate:
                            estate = 'Unknown'
                        
                        # Get monthly fee
                        try:
                            monthly_fee = float(row.get('monthly_fee', 500)) if pd.notna(row.get('monthly_fee')) else 500
                        except:
                            monthly_fee = 500
                        
                        # Create customer
                        customer = Customer(
                            full_name=full_name,
                            phone_number=phone,
                            email=email,
                            address=address,
                            estate=estate,
                            monthly_fee=monthly_fee,
                            is_active=True
                        )
                        customer.save()
                        imported_count += 1
                        
                    except Exception as e:
                        skipped_count += 1
                        errors.append(f"Row {index+2}: {str(e)}")
                
                # Show success message
                if imported_count > 0:
                    messages.success(request, f'Successfully imported {imported_count} customers!')
                
                if skipped_count > 0:
                    messages.warning(request, f'Skipped {skipped_count} rows.')
                    for error in errors[:5]:  # Show first 5 errors
                        messages.error(request, error)
                    if len(errors) > 5:
                        messages.info(request, f'And {len(errors) - 5} more errors. Check the import log.')
                
                return redirect('core:customer_list')
                
            except Exception as e:
                messages.error(request, f'Error reading file: {str(e)}')
                return redirect('core:customer_import')
    else:
        form = CustomerImportForm()
    
    return render(request, 'core/customer_import.html', {'form': form})

@user_passes_test(is_admin)
def customer_detail(request, customer_id):
    customer = get_object_or_404(Customer, id=customer_id)
    payments = Payment.objects.filter(customer=customer, status='COMPLETED').order_by('-payment_date')
    
    context = {
        'customer': customer,
        'payments': payments,
        'total_paid': customer.total_paid,
        'pending_bills': customer.pending_bills,
    }
    
    return render(request, 'core/customer_detail.html', context)