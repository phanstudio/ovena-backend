from .otp_views import VerifyOTPView, VerifyEmailOTPView, SendEmailOTPView, SendPhoneOTPView # noqa: F401
from .account_views import (
    RegisterCustomer, LinkApproveView, LinkRequestCreateView, # noqa: F401
    UserProfileView, DeleteAccountView, UpdateBranch, Delete2AccountView, # noqa: F401
    UpdateCustomer, PasswordResetView, AdminLoginView, # noqa: F401
    DriverLoginView, StaffLoginView # noqa: F401
)
from .oath_views import OAuthExchangeView # noqa: F401
import accounts.views.jwt_views  # noqa: F401

# from .auth_views import LoginView, RegisterView
# from .restaurant_views import RestaurantListView
# from .order_views import OrderCreateView, OrderDetailView
