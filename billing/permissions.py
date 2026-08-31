from common.permissions import HasCapabilityForMethod


class HasBillingCapability(HasCapabilityForMethod):
    """403 when the caller holds no capability for this billing module.

    Role permission only. Feature availability is checked separately by
    `FeatureGatedAPIMixin`, and object scope separately again in
    `billing/selectors.py`. A viewset that also sets
    `required_write_capabilities` gets a second, write-only gate on top —
    see `HasCapabilityForMethod`.
    """
