from django.core.files.storage import storages

class PrivateStorage:
    def __new__(cls, *args, **kwargs):
        return storages["private"]
