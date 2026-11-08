from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('login/', auth_views.LoginView.as_view(template_name='accounts/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('activate/', views.activate_account_view, name='activate_account'),
    path('password/reset/', views.password_reset_request_view, name='password_reset_request'),
    path('password/reset/confirm/', views.password_reset_confirm_view, name='password_reset_confirm'),
]