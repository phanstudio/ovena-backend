from .otp_views import SendOTPView, VerifyOTPView
from .account_views import (
    RegisterCustomer, RegisterRManager, LinkApprove, LinkRequestCreate, 
    UserProfileView, DeleteAccountView, UpdateBranch, Delete2AccountView,
    UpdateCustomer
)
from .oath_views import OAuthExchangeView
import accounts.views.jwt_views

# from .auth_views import LoginView, RegisterView
# from .restaurant_views import RestaurantListView
# from .order_views import OrderCreateView, OrderDetailView
