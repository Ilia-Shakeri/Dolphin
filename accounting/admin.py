"""Operator-only inspection, not a customer-facing surface (CLAUDE.md §5.4
distinguishes the two). Registered so a developer can inspect phase-1 data
directly once this app is wired into INSTALLED_APPS — not itself part of
that wiring.
"""

from django.contrib import admin

from accounting.models import Account, JournalEntry, JournalLine


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "account_type", "is_active", "allow_manual_posting")
    list_filter = ("account_type", "is_active")
    search_fields = ("code", "name")


class JournalLineInline(admin.TabularInline):
    model = JournalLine
    extra = 0


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ("reference", "entry_date", "memo", "created_by")
    inlines = [JournalLineInline]
