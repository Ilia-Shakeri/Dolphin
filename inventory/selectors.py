from accounts.models import User
from inventory.models import StockItem, StockMovement, Warehouse


ELEVATED_OPERATIONAL = {User.Role.SALES_MANAGER, User.Role.COMPANY_IT, User.Role.PLATFORM_ADMIN}


def _reads_inventory(user):
    """Inventory is company-wide data, so scope is by role, not by row owner.

    A Sales Agent in the `sales` workstream may read it (they need to know
    whether a product can be sold) and may change nothing. An after-sales
    operator sees none of it, matching every other sales-side selector.
    """
    if user.role == User.Role.SALES_AGENT:
        return user.workstream != User.Workstream.AFTER_SALES
    return user.role in ELEVATED_OPERATIONAL


def warehouses_for(user):
    queryset = Warehouse.objects.all()
    if not _reads_inventory(user):
        return queryset.none()
    if user.role == User.Role.SALES_AGENT:
        return queryset.filter(is_active=True)
    return queryset


def stock_items_for(user):
    queryset = StockItem.objects.all()
    if not _reads_inventory(user):
        return queryset.none()
    if user.role == User.Role.SALES_AGENT:
        return queryset.filter(warehouse__is_active=True, product__is_active=True)
    return queryset


def stock_movements_for(user):
    queryset = StockMovement.objects.all()
    if not _reads_inventory(user):
        return queryset.none()
    return queryset


def available_quantity(*, product, warehouse=None):
    """Current on-hand quantity for a product, optionally in one warehouse."""
    queryset = StockItem.objects.filter(product=product)
    if warehouse is not None:
        queryset = queryset.filter(warehouse=warehouse)
    total = 0
    for value in queryset.values_list("quantity", flat=True):
        total += value
    return total
