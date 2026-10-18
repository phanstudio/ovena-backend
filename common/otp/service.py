"""
Multi-channel OTP dispatch service with automated carrier fallback.
Orchestrates SMS delivery with automated email fallback on carrier/provider failure.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
import logging
from common.otp.base import OTPManager
from common.otp.exceptions import OTPDeliveryError

logger = logging.getLogger(__name__)


class BaseMultiChannelOTPService(ABC):
    """
    Abstract base service defining the contract for multi-channel / multi-cast OTP delivery.
    """

    @classmethod
    @abstractmethod
    def send_with_fallback(
        cls,
        phone_number: str | None,
        email: str | None,
        prefer_email: bool = False,
    ) -> dict:
        """
        Deliver OTP across channels with automated fallback capability.
        Returns:
            {"channel_used": str, "fallback": bool}
        """
        pass


class MultiChannelOTPService(BaseMultiChannelOTPService):
    """
    High-level OTP delivery service that coordinates channel fallback policies.
    """

    @classmethod
    def send_with_fallback(
        cls,
        phone_number: str | None,
        email: str | None,
        prefer_email: bool = False,
    ) -> dict:
        """
        Sends an OTP code.
        - If prefer_email is True and email is provided, sends via email.
        - Otherwise attempts SMS delivery first; if SMS fails due to delivery
          error or carrier failure, automatically falls back to email delivery.
        
        Returns:
            {"channel_used": "phone" | "email", "fallback": bool}
        """
        if prefer_email and email:
            OTPManager.send(channel="email", identifier=email)
            return {"channel_used": "email", "fallback": False}

        if phone_number:
            try:
                OTPManager.send(channel="phone", identifier=phone_number)
                return {"channel_used": "phone", "fallback": False}
            except (OTPDeliveryError, Exception) as exc:
                logger.warning(
                    "SMS delivery failed for %s, falling back to email: %s",
                    phone_number,
                    exc,
                )
                if email:
                    OTPManager.send(channel="email", identifier=email)
                    return {"channel_used": "email", "fallback": True}
                raise exc

        if email:
            OTPManager.send(channel="email", identifier=email)
            return {"channel_used": "email", "fallback": False}

        raise ValueError("Neither phone number nor email was provided for OTP delivery.")
