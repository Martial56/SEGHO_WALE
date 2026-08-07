from django.contrib import admin

from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'centre_actif', 'session_timeout_minutes']
    list_filter = ['centres', 'centre_actif']
    search_fields = ['user__username', 'user__first_name', 'user__last_name']
    filter_horizontal = ['centres']
