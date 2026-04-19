# todo
# class AdminReferralUserListView(ListAPIView): # only show if the user converted is above 10 after been minused by the payed
#     ...

# class AdminReferralPaymentVew():
#     ...
# to do the calculation agregate will be use to count the converted per user that aren't marked as completed;

# add pay partial the amount / required amount 1, means 10 are converted;
# add pay all sets all to converted via bulk update 

# referrals/admin_views.py
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.db.models import Count, Q

from admin_api.views import BaseAppAdminAPIView
from referrals.services import process_referral_payout, verify_snapshot_integrity, REFERRALS_PER_UNIT
from referrals.serializers import AdminReferralPaymentSerializer
from django.shortcuts import get_object_or_404

User = get_user_model()


class AdminReferralUserListView(BaseAppAdminAPIView):

    def get(self, request):
        qs = (
            User.objects
            .annotate(
                unpaid=Count(
                    "profile_referrals_made",
                    filter=Q(
                        profile_referrals_made__converted_at__isnull=False,
                        profile_referrals_made__is_consumed=False
                    )
                )
            )
            .filter(unpaid__gte=REFERRALS_PER_UNIT)
            .order_by("-unpaid")
        )

        data = [
            {
                "user_id": u.id,
                "email": getattr(u, "email", None),
                "unpaid_conversions": u.unpaid,
                "eligible_units": u.unpaid // REFERRALS_PER_UNIT,
            }
            for u in qs
        ]

        return Response(data)

class AdminReferralPaymentView(BaseAppAdminAPIView):
    serializer_class = AdminReferralPaymentSerializer

    def post(self, request):
        vd = self.validate_serializer()
        units = vd["units"]
        
        user = get_object_or_404(User, id=vd['user_id'])

        payout = process_referral_payout(
            user=user,
            units=int(units) if units else None,
            mode=vd["mode"]
        )

        return Response({
            "payout_id": payout.id,
            "units_paid": payout.units_paid,
            "referrals_used": payout.referrals_used,
        })

class AdminVerifyPayoutView(BaseAppAdminAPIView):

    def get(self, request, payout_id):
        from referrals.models import ReferralPayout

        payout = ReferralPayout.objects.get(id=payout_id)

        is_valid = verify_snapshot_integrity(payout)

        return Response({
            "payout_id": payout.id,
            "is_valid": is_valid,
        })
