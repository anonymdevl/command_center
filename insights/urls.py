from django.contrib import admin
from django.urls import path, re_path

from insights.core import views

admin.site.site_header = "Platform administration"
admin.site.site_title = "Platform administration"
admin.site.index_title = "Businesses, people and settings"
# Before admin.site.urls is read: its sign-in page gets the platform's attempt limits.
admin.site.login = views.admin_login

urlpatterns = [
    path("", views.home),
    path("admin/", admin.site.urls),
    re_path(r"^api/method/(?P<method>[\w.]+)/?$", views.api_method),
    path("command-center-login", views.command_center_login),
    path("management-only", views.management_only),
    path("command-center-access", views.command_center_access),
    re_path(r"^command-center(?:/(?P<path>.*))?$", views.command_center),
    re_path(r"^assets/command_center/(?P<path>.+)$", views.assets),
    re_path(r"^branding/(?P<name>[^/]+)$", views.branding_file),
]
