from django.urls import path


class BaseBranchRouter:
    """
    Abstract router for branch based endpoints.
    """

    def __init__(self, prefix=""):
        self.prefix = prefix

    def register(self, route, view, basename=None):
        urls = []

        base = f"{self.prefix}{route}/"

        basename = basename or f"{base}".strip("/").replace("/", "-").lower()

        urls += [
            path(base, view.as_view(), name=basename),
            path(f"{self.prefix}<int:branch_id>/{route}/", view.as_view(), name=f"{basename}-admin"),
        ]

        return urls
