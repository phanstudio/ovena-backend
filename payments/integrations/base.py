from abc import ABC, abstractmethod

class BasePaymentClient(ABC):

    @abstractmethod
    def initialize_transaction(self, payload):
        pass

    @abstractmethod
    def verify_transaction(self, reference):
        pass

    @abstractmethod
    def create_customer(self, payload):
        pass

    @abstractmethod
    def create_subscription(self, payload):
        pass

    @abstractmethod
    def cancel_subscription(self, payload):
        pass