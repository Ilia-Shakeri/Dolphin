from common.permissions import HasCapabilityForMethod


class HasSalesCapability(HasCapabilityForMethod):
    """Answer 403 when the caller holds no capability for this module.

    Without this, a caller with no capability at all received `200` with an
    empty page, because the selectors return an empty queryset for them. That
    was never a data leak — the boundary held, and direct-ID access already
    answered `404` — but it was inconsistent with `users`, `activity-logs`, and
    `inbound-sms`, which answer `403`. An after-sales operator asking for
    customers is not asking for an empty list; they are asking for something
    they may not have.

    This is role permission only. Feature availability is checked separately by
    `FeatureGatedAPIMixin`, and object scope separately again by each selector.
    A viewset that also sets `required_write_capabilities` gets a second,
    write-only gate on top — see `HasCapabilityForMethod`.
    """
