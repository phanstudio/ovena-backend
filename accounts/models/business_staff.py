from django.db import models
from accounts.models  import Branch, User, PrimaryAgent, BusinessAdmin

class PrimaryAgentAction(models.TextChoices):
    ASSIGNED = "assigned", "Assigned"
    REVOKED = "revoked", "Revoked"
    RECLAIMED = "reclaimed", "Reclaimed"  # a user's existing agent identity was moved to a new branch
    UNREVOKED = "unrevoked", "Unrevoked"  # flipped back on with no other changes (device/user unchanged)


class PrimaryAgentHistory(models.Model):
    """
    Append-only audit trail of PrimaryAgent assignment changes.

    PrimaryAgent itself is a *live* row: exactly one per branch and exactly
    one per user, reused and mutated forever (see unique_primary_agent_per_branch
    and the user OneToOneField). That means the live table can never answer
    "who was the agent at branch X on date Y" — this table can, because it's
    never overwritten and never deleted.

    Fields are intentionally denormalized (branch, device_name, name stored
    directly) rather than trusted to `primary_agent`, since that row may be
    deleted or repurposed for a different branch after this history entry
    is written.
    """

    branch = models.ForeignKey(
        Branch, on_delete=models.CASCADE, related_name="primary_agent_history"
    )
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="primary_agent_history"
    )
    # May become null if the live row is later deleted (e.g. reclaimed onto
    # another branch and the stale row is dropped) - that's expected and fine,
    # this history row still stands on its own via the fields above.
    primary_agent = models.ForeignKey(
        PrimaryAgent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="history",
    )
    device_name = models.CharField(max_length=200)
    name = models.CharField(max_length=200)
    action = models.CharField(max_length=20, choices=PrimaryAgentAction.choices)
    created_by = models.ForeignKey(
        BusinessAdmin, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["branch", "-created_at"]),
            models.Index(fields=["user", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.action} - {self.branch.name} - {self.device_name} @ {self.created_at}"


def record_primary_agent_history(*, branch, user, primary_agent, device_name, name, action, created_by):
    return PrimaryAgentHistory.objects.create(
        branch=branch,
        user=user,
        primary_agent=primary_agent,
        device_name=device_name,
        name=name,
        action=action,
        created_by=created_by,
    )
