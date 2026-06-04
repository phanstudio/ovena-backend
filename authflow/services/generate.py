import secrets
import string


def generate_passphrase():
    words = ["mango", "horse", "bright", "storm", "leaf", "river", "cloud", "stone"]
    return "-".join(secrets.choice(words) for _ in range(2)) + "-" + str(secrets.randbelow(99))

def generate_referral_code(length=8):
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))
