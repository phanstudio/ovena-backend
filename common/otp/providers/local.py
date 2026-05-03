from .base import BaseOTPBackend
class LocalOTPBackend(BaseOTPBackend):

    def send(self, identifier):
        ...

    def verify(self, identifier, code, context=None):
        ...



