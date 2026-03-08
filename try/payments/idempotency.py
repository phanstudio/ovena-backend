from __future__ import annotations

import hashlib
import json

from django.db import transaction

from payments.models import PaymentIdempotencyKey


class IdempotencyConflictError(ValueError):
    pass


def _stable_hash(payload: dict) -> str:
    canonical = json.dumps(payload or {}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@transaction.atomic
def begin_idempotent_request(scope: str, actor_id: str, key: str, payload: dict):
    request_hash = _stable_hash(payload)
    row = PaymentIdempotencyKey.objects.select_for_update().filter(scope=scope, actor_id=str(actor_id), key=key).first()
    if row:
        if row.request_hash != request_hash:
            raise IdempotencyConflictError("Idempotency-Key already used with a different payload")
        return row, bool(row.response_snapshot)

    row = PaymentIdempotencyKey.objects.create(
        scope=scope,
        actor_id=str(actor_id),
        key=key,
        request_hash=request_hash,
    )
    return row, False


@transaction.atomic
def save_idempotent_response(row: PaymentIdempotencyKey, response_snapshot: dict):
    row.response_snapshot = response_snapshot
    row.save(update_fields=["response_snapshot", "updated_at"])
