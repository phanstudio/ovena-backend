"""
payments/points/tasks.py

No celery-beat needed. Trigger this from system cron instead:

    5 0 1 * *  cd /path/to/project && python manage.py shell -c \
        "from payments.points.tasks import finalize_leaderboard_task; finalize_leaderboard_task.delay()"

Or, cleaner, give cron a one-line management command that just calls
.delay() (see finalize_leaderboard.py --async). Either way, cron is the
scheduler; celery is just the execution/retry engine here.

If more scheduled jobs show up later and this pattern starts feeling
duct-taped, that's the point to add django-celery-beat -- it's a small
addition on top of an existing celery setup and gets you DB-managed
schedules instead of N cron lines.
"""

from datetime import date

from celery import shared_task
from django.contrib.auth import get_user_model

from points import leaderboard_service, service

User = get_user_model()

# Shared retry policy for the award tasks. acks_late means the broker only
# marks a task done once it actually finishes -- if a worker dies mid-task,
# the message is redelivered. That makes "at least once" delivery the norm,
# which is exactly why every award_* call requires an idempotency_key: a
# redelivered/retried task must be safe to run twice.
_AWARD_TASK_KWARGS = dict(
    bind=True,
    max_retries=5,
    retry_backoff=True,      # exponential backoff between retries
    retry_backoff_max=600,   # cap backoff at 10 minutes
    retry_jitter=True,
    acks_late=True,
)


@shared_task(**_AWARD_TASK_KWARGS)
def award_referral_success_task(self, referrer_id: str, referred_user_id: str, idempotency_key: str):
    try:
        referrer = User.objects.get(id=referrer_id)
        referred_user = User.objects.get(id=referred_user_id)
    except User.DoesNotExist:
        # The referenced row is gone -- retrying won't fix that, so don't loop.
        return
    try:
        service.award_referral_success(
            referrer=referrer, referred_user=referred_user, idempotency_key=idempotency_key
        )
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(**_AWARD_TASK_KWARGS)
def award_referred_first_order_task(self, referred_id: str, sale_id: str, idempotency_key: str):
    from payments.models import Sale  # local import avoids a hard app-loading-order dependency
    from referrals.models import ProfileReferral

    try:
        # referrer = User.objects.get(id=referrer_id)
        referral = ProfileReferral.objects.select_related("user").get(referee_user_id=referred_id)
        referrer = referral.referrer_user#User.objects.get(id=referral.referrer_user.id)
        sale = Sale.objects.get(id=sale_id)
    except (User.DoesNotExist, Sale.DoesNotExist):
        return
    try:
        service.award_referred_first_order(referrer=referrer, sale=sale, idempotency_key=idempotency_key)
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(**_AWARD_TASK_KWARGS)
def award_order_streak_task(self, user_id: str, sale_id: str, streak_count: int, idempotency_key: str):
    from payments.models import Sale

    try:
        user = User.objects.get(id=user_id)
        sale = Sale.objects.get(id=sale_id)
    except (User.DoesNotExist, Sale.DoesNotExist):
        return
    try:
        service.award_order_streak(
            user=user, sale=sale, streak_count=streak_count, idempotency_key=idempotency_key
        )
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(**_AWARD_TASK_KWARGS)
def award_order_milestone_scratch_card_task(
    self, user_id: str, sale_id: str, order_number: int, scratched_points: int, idempotency_key: str
):
    from payments.models import Sale

    try:
        user = User.objects.get(id=user_id)
        sale = Sale.objects.get(id=sale_id)
    except (User.DoesNotExist, Sale.DoesNotExist):
        return
    try:
        service.award_order_milestone_scratch_card(
            user=user,
            sale=sale,
            order_number=order_number,
            scratched_points=scratched_points,
            idempotency_key=idempotency_key,
        )
    except ValueError:
        # Bad input (out-of-range points, wrong order_number) -- retrying
        # with the same bad args will never succeed, so don't retry.
        raise
    except Exception as exc:
        raise self.retry(exc=exc)


def award_order_branch_rated_task(_self, user_id: str, rating_id: str, _idempotency_key: str):
    from ratings.models import BranchRating

    try:
        user = User.objects.get(id=user_id)
        rating = BranchRating.objects.get(id=rating_id)
        return (user, rating)
    except (User.DoesNotExist, BranchRating.DoesNotExist):
        return


def award_order_driver_rated_task(_self, user_id: str, rating_id: str, _idempotency_key: str):
    from ratings.models import DriverRating

    try:
        user = User.objects.get(id=user_id)
        rating = DriverRating.objects.get(id=rating_id)
        return (user, rating)
    except (User.DoesNotExist, DriverRating.DoesNotExist):
        return

# make for driver or ask about which type if one one rating counts;
@shared_task(**_AWARD_TASK_KWARGS)
def award_order_rated_task(self, user_id: str, rating_id: str, idempotency_key: str, rating_type:str):
    
    result = None
    if rating_type == "branch":
        result = award_order_branch_rated_task(self, user_id, rating_id, idempotency_key)
    else:
        result = award_order_driver_rated_task(self, user_id, rating_id, idempotency_key)
    
    if not result:
        return
    user, rating = result
    try:
        service.award_order_rated(user=user, rating=rating, idempotency_key=idempotency_key)
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def finalize_leaderboard_task(self, period_str: str | None = None):
    period = None
    if period_str:
        year, month = (int(p) for p in period_str.split("-"))
        period = date(year, month, 1)

    try:
        snapshot = leaderboard_service.finalize_leaderboard_for_period(period)
    except Exception as exc:  # transient DB issues etc.
        raise self.retry(exc=exc)

    return {"period": str(snapshot.period_start), "entry_count": snapshot.entries.count()}
