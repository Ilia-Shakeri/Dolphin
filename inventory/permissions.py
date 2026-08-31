from common.permissions import HasCapabilityForMethod


class HasInventoryCapability(HasCapabilityForMethod):
    """403 when the caller holds no inventory capability at all.

    Role permission only. Feature availability is checked separately by
    `FeatureGatedAPIMixin`, and object scope separately again in the
    selectors. A viewset that also sets `required_write_capabilities` gets a
    second, write-only gate on top — see `HasCapabilityForMethod`.
    """
