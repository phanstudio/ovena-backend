import json
import logging
import time
import asyncio

from django.utils import timezone
from django.db.models import OuterRef
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

from menu.models import OrderEvent
from accounts.models import User
from accounts.services.profiles import (
    PROFILE_CUSTOMER,
    PROFILE_DRIVER,
    PROFILE_BUSINESS_STAFF,
    get_profile,
)

logger = logging.getLogger(__name__)

# ── close codes ──────────────────────────────────────────────────────────────
CLOSE_UNAUTHENTICATED = 4001
CLOSE_FORBIDDEN       = 4003
CLOSE_RATE_LIMITED    = 4429
CLOSE_SERVER_ERROR    = 4500
CLOSE_GOING_AWAY      = 1001   # normal; client should reconnect

# ── heartbeat tunables ────────────────────────────────────────────────────────
PING_INTERVAL   = 25   # seconds between server pings
PONG_TIMEOUT    = 10   # seconds to wait for client pong


class BaseConsumer(AsyncWebsocketConsumer):
    """Base consumer with authentication utilities"""

    @database_sync_to_async
    def check_is_driver(self, user):
        """Check if user is a driver"""
        if not isinstance(user, User):
            return False
        return get_profile(user, PROFILE_DRIVER) is not None
    
    @database_sync_to_async
    def check_is_branch_staff(self, user): # add for the resturant staffs
        """Check if user is branch staff"""
        if isinstance(user, User):
            return get_profile(user, PROFILE_BUSINESS_STAFF) is not None
        return False
    
    @database_sync_to_async
    def check_is_customer(self, user):
        """Check if user is a customer"""
        if not isinstance(user, User):
            return False
        return get_profile(user, PROFILE_CUSTOMER) is not None

    @database_sync_to_async
    def get_driver_profile(self, user):
        if not isinstance(user, User):
            return None
        return get_profile(user, PROFILE_DRIVER)

    @database_sync_to_async
    def get_customer_profile(self, user):
        if not isinstance(user, User):
            return None
        return get_profile(user, PROFILE_CUSTOMER)

    @database_sync_to_async
    def get_branch_staff(self, user):
        if isinstance(user, User):
            return get_profile(user, PROFILE_BUSINESS_STAFF)
        return None

    def _load_json(self, text_data):
        try:
            return json.loads(text_data)
        except json.JSONDecodeError as exc:
            logger.warning("invalid websocket JSON payload (%s): %s", self.channel_name, exc)
            return None
    
    async def connect(self):
        # Fast channel-layer health check before doing any DB work
        # if not await self._layer_ok():
        #     await self.close(code=CLOSE_SERVER_ERROR)
        #     return

        ok = await self.connect_func()
        if ok:
            self._ping_seq        = 0
            # self._last_pong_time = time.time()
            # self._heartbeat_task  = asyncio.create_task(self._heartbeat_loop())

    async def connect_func(self):
        ...

    async def disconnect(self, close_code):
        if hasattr(self, "_heartbeat_task"):
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        await self.disconnect_func(close_code)

    async def disconnect_func(self, close_code):
        ...

    async def receive(self, text_data):
        data = self._load_json(text_data)
        if data is None:
            return

        message_type = data.get("type")

        # ── heartbeat ──────────────────────────────────────────────────────
        if message_type == "pong":
            self._last_pong_time = time.time()
            return

        if message_type == "ping":
            await self._send_json({"type": "pong", "seq": data.get("seq", 0)})
            return

        # ── missed-event replay ────────────────────────────────────────────
        # if message_type == "replay" and self.SUPPORTS_REPLAY:
        #     since_ts = data.get("since", 0)
        #     await self._replay_missed_events(since_ts)
        #     return

        await self.receive_func(message_type, data)

    async def receive_func(self, message_type, data):
        ...

    # ── heartbeat loop ────────────────────────────────────────────────────────

    # async def _heartbeat_loop(self):
    #     """
    #     Sends a server ping every PING_INTERVAL seconds.
    #     If the client doesn't pong within PONG_TIMEOUT seconds, the
    #     connection is considered dead and is closed.
    #     """
    #     try:
    #         while True:
    #             await asyncio.sleep(PING_INTERVAL)

    #             if not self._pong_received:
    #                 # Previous ping was not answered — zombie connection
    #                 logger.warning(
    #                     "No pong from %s (seq=%s) — closing zombie",
    #                     self.channel_name, self._ping_seq,
    #                 )
    #                 await self.close(code=CLOSE_GOING_AWAY)
    #                 return

    #             self._ping_seq      += 1
    #             self._pong_received  = False

    #             await self._send_json({"type": "ping", "seq": self._ping_seq})

    #             # Give the client PONG_TIMEOUT seconds to reply
    #             await asyncio.sleep(PONG_TIMEOUT)

    #     except asyncio.CancelledError:
    #         pass
    #     except Exception:
    #         # Connection already gone
    #         pass

    async def _heartbeat_loop(self):
        try:
            while True:
                await asyncio.sleep(PING_INTERVAL)

                now = time.time()

                # if client hasn't responded in time → close
                if now - self._last_pong_time > (PING_INTERVAL + PONG_TIMEOUT):
                    logger.warning(
                        "No pong from %s — closing connection",
                        self.channel_name,
                    )
                    await self.close(code=CLOSE_GOING_AWAY)
                    return

                self._ping_seq += 1

                await self._send_json({
                    "type": "ping",
                    "seq": self._ping_seq
                })

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("Heart beat error (%s): %s", self.channel_name, e)

    # ── missed-event replay ───────────────────────────────────────────────────

    # async def _replay_missed_events(self, since_ts: float):
    #     """Override in subclasses to replay from the right groups."""
    #     pass

    # ── channel-layer health ──────────────────────────────────────────────────

    # async def _layer_ok(self) -> bool:
    #     try:
    #         await asyncio.wait_for(
    #             self.channel_layer.group_add("__health__", "__health__"),
    #             timeout=2.0,
    #         )
    #         await self.channel_layer.group_discard("__health__", "__health__")
    #         return True
    #     except Exception:
    #         logger.error("Channel layer health check failed")
    #         return False

    async def _send_json(self, payload: dict):
        try:
            await self.send(text_data=json.dumps(payload, default=str))
        except Exception as e:
            logger.warning("WebSocket send failed (%s): %s", self.channel_name, e)

    def last_order_event_subquery(self):
        return OrderEvent.objects.filter(
            order_id=OuterRef('pk')
        ).order_by('-timestamp')
