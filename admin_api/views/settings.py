from decimal import Decimal
from rest_framework.response import Response

from payments.models import PlatformConfig
from admin_api.models import AppAdmin
from admin_api.serializers import AdminSystemSettingsSerializer
from .base import BaseAppAdminAPIView, _AppAdminRoleGuardMixin


class AdminSystemSettingsView(BaseAppAdminAPIView, _AppAdminRoleGuardMixin):
    """
    GET, PATCH /api/admin/settings/
    Manage platform-wide settings (fees, commissions, delivery radius, maintenance mode).
    (Note: Holiday mode excluded per specification).
    """
    allowed_roles = {
        AppAdmin.Role.ADMIN,
        AppAdmin.Role.SUPERVISOR,
        AppAdmin.Role.OWNER,
        AppAdmin.Role.OPERATIONS,
    }
    serializer_class = AdminSystemSettingsSerializer

    CONFIG_DEFAULTS = {
        "service_fee_percent": "4.0",
        "delivery_base_fee_ngn": "500.00",
        "restaurant_commission_percent": "10.0",
        "referral_reward_ngn": "1000.00",
        "minimum_order_ngn": "1500.00",
        "delivery_radius_km": "15.0",
        "maintenance_mode": "false",
    }

    def get(self, request):
        configs = {}
        for key, default in self.CONFIG_DEFAULTS.items():
            configs[key] = PlatformConfig.get(key, default=default)

        return Response({
            "service_fee_percent": float(configs["service_fee_percent"]),
            "delivery_base_fee_ngn": Decimal(configs["delivery_base_fee_ngn"]),
            "restaurant_commission_percent": float(configs["restaurant_commission_percent"]),
            "referral_reward_ngn": Decimal(configs["referral_reward_ngn"]),
            "minimum_order_ngn": Decimal(configs["minimum_order_ngn"]),
            "delivery_radius_km": float(configs["delivery_radius_km"]),
            "maintenance_mode": configs["maintenance_mode"].lower() == "true",
        })

    def patch(self, request):
        self._require_app_admin_roles(request, self.allowed_roles)
        vd = self.validate_serializer(request.data)

        updated = {}
        for key, val in vd.items():
            if val is not None:
                val_str = str(val).lower() if isinstance(val, bool) else str(val)
                PlatformConfig.objects.update_or_create(
                    key=key,
                    defaults={"value": val_str, "description": f"System setting: {key}"}
                )
                updated[key] = val

        return Response({
            "detail": "System settings updated successfully",
            "updated": updated,
        })
