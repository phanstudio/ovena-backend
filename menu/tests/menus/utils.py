from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken


def cprint(*objects: any, engine_config="json") -> any:
    from pprint import pprint
    import json

    match engine_config:
        case "json":
            engine = lambda item: print(json.dumps(item, indent=2))
        case "pp":
            engine = lambda item: pprint(item)
        case _:
            print("invalid engine")
            engine = lambda item: print(item)

    for obj in objects:
        engine(obj)

def authenticate(client, user):
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return client



