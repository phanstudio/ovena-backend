# ─── Exceptions ──────────────────────────────────────────────────────────────

class OTPError(Exception):
    """Base class for all OTP errors. Always safe to catch at the top level."""
    pass

class OTPRateLimitError(OTPError):
    """Raised when a channel's send rate limit is exceeded."""
    pass

class OTPGenerationError(OTPError):
    """Raised when a unique OTP cannot be generated (cache collision)."""
    pass

class OTPInvalidError(OTPError):
    """Raised when the supplied code is wrong or has already expired."""
    pass

class OTPDeliveryError(OTPError):
    """Raised when the underlying transport (email/SMS) fails to send."""
    pass
