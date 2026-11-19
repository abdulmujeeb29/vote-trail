from django.contrib import admin

from .models import Job


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("id", "kind", "status", "attempts", "run_after", "updated_at")
    list_filter = ("status", "kind")
    readonly_fields = [f.name for f in Job._meta.fields]
