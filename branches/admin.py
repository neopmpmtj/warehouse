from django.contrib import admin

from .models import Branch, BranchMembership


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "created_at")


@admin.register(BranchMembership)
class BranchMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "branch", "role")
    list_filter = ("branch", "role")
