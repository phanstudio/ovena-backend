class BaseOTPBackend:
    def send(self, identifier):
        raise NotImplementedError

    def verify(self, identifier, code, context=None):
        raise NotImplementedError