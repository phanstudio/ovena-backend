from accounts.models import User

def get_phone_number(user: User):
    return str(user.phone_number) if user.phone_number else None