from accounts.models import Penalty, Appeal, User


def record_penalty(*, user, role, reason, issued_by=None, issuer_type=None):
    Penalty.objects.create(
        user=user,
        reason=reason,
        issued_by=issued_by,
        role=role,
        issuer_type=issuer_type or Penalty.ISSUER_SUPPORT,
    )

def record_system_penalty(*, user, role, reason):
    record_penalty(user=user, role=role, reason=reason, issuer_type=Penalty.ISSUER_SYSTEM)

def record_sales_penalty(sale, order):
    from payments.models import Sale

    if sale.responsible_party == Sale.RESPONSIBLE_BUSINESS:
        user = User.objects.filter(primary_agent__id=order.branch.primary_agent_id)
        record_system_penalty(user=user, reason=sale.refund_reason)
    if sale.responsible_party == Sale.RESPONSIBLE_DRIVER:
        record_system_penalty(user=sale.driver, reason=sale.refund_reason)

# notify the parties involved;
# disable the through jwts and ue quick cache for window when jwt is invalid..
