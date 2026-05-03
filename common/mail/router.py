import logging
from .providers import get_email_providers

logger = logging.getLogger(__name__)


class EmailRouter:
    """
    Sends email using multiple providers with automatic failover.
    """

    def __init__(self):
        self.backends = get_email_providers()

    def send(self, message):
        last_exception = None

        for provider_name, backend in self.backends:
            try:
                sent_count = backend.send_messages([message])

                if sent_count:
                    logger.info(
                        f"Email sent using {provider_name}"
                    )

                    return {
                        "success": True,
                        "provider": provider_name,
                    }

            except Exception as exc:
                last_exception = exc

                logger.exception(
                    f"Email provider failed: {provider_name}"
                )

        return {
            "success": False,
            "error": str(last_exception),
        }
