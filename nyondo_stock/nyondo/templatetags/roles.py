# nyondo/templatetags/roles.py
from django import template

register = template.Library()

@register.filter
def job_title(user):
    if not user or not user.is_authenticated:
        return ""
    if getattr(user, "is_superuser", False):
        return "Super Admin"

    g = user.groups.first()
    if not g:
        return "User"

    # map group names to nice labels
    mapping = {
        "SALES_ATTENDANT": "Sales Attendant",
        "STORE_MANAGER": "Store Manager",
        "ACCOUNTS_ADMIN": "Accounts/Admin",
    }
    return mapping.get(g.name, g.name)