from accounts.models import User
from phonenumbers import PhoneNumber

def get_phone_number(number_carrier: User|PhoneNumber):
    if isinstance(number_carrier, User):
        return str(number_carrier.phone_number) if number_carrier.phone_number else None
    else:
        return str(number_carrier)