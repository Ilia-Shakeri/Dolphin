from common.permissions import HasCapabilityForMethod


class HasAfterSalesCapability(HasCapabilityForMethod):
    """403 when the caller holds no after-sales capability at all.

    Before this, a caller with none of `after_sales.company` (elevated
    roles) or `after_sales.assigned` (the after-sales workstream agent)
    received `200` with an empty page, because `after_sales_requests_for`
    returns `.none()` for everyone else. `sales.permissions.HasSalesCapability`
    fixed this same inconsistency for `customers`/`leads`/etc. a while ago —
    this closes the one module that was still exempt.
    """
