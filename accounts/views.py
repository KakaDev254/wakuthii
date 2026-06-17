from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from .forms import CustomerLoginForm

def admin_login(request):
    """Custom admin login page"""
    if request.user.is_authenticated and (request.user.is_superuser or request.user.is_staff):
        return redirect('core:admin_dashboard')
    
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            
            if user is not None:
                if user.is_superuser or user.is_staff:
                    login(request, user)
                    messages.success(request, f'Welcome back, {user.username}!')
                    return redirect('core:admin_dashboard')
                else:
                    messages.error(request, 'You do not have admin access.')
            else:
                messages.error(request, 'Invalid username or password.')
        else:
            messages.error(request, 'Invalid username or password.')
    
    form = AuthenticationForm()
    return render(request, 'accounts/admin_login.html', {'form': form})

@login_required
def admin_logout(request):
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('core:home')