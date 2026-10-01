# referrals/constants.py

ROLE_CUSTOMER = "customer"
ROLE_DRIVER = "driver"
ROLE_BUSINESS_ADMIN = "businessadmin"  # Reserved for future phase
ROLE_BUSINESS_STAFF = "businessstaff"

REFERRAL_ROLE_CHOICES = [
    (ROLE_CUSTOMER, "Customer"),
    (ROLE_DRIVER, "Driver"),
]

# Active programs: currently only Customer and Driver are supported
SUPPORTED_REFERRER_ROLES = {ROLE_CUSTOMER, ROLE_DRIVER}
SUPPORTED_REFEREE_ROLES = {ROLE_CUSTOMER, ROLE_DRIVER}

FRAUD_STATUS_CLEAN = "clean"
FRAUD_STATUS_FLAGGED = "flagged"
FRAUD_STATUS_REJECTED = "rejected"

FRAUD_STATUS_CHOICES = [
    (FRAUD_STATUS_CLEAN, "Clean"),
    (FRAUD_STATUS_FLAGGED, "Flagged"),
    (FRAUD_STATUS_REJECTED, "Rejected"),
]

# Anti-cheat thresholds
MAX_REFERRALS_PER_IP_24H = 3
MIN_QUALIFYING_ORDER_AMOUNT_KOBO = 150000  # ₦1,500 minimum qualifying order
REFERRALS_PER_UNIT = 10
