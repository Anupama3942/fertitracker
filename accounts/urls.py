from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('login/', views.login_view, name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('officers/', views.admin_officers_view, name='admin_officers'),
    path('activate/', views.activate_account_view, name='activate_account'),
    path('password/reset/', views.password_reset_request_view, name='password_reset_request'),
    path('password/reset/confirm/', views.password_reset_confirm_view, name='password_reset_confirm'),
    path('password/force-change/', views.force_password_change_view, name='force_password_change'),
    path('seasons/<int:season_id>/toggle/', views.toggle_season_status, name='toggle_season_status'),
]