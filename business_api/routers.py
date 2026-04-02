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
    
# class BaseBranchRouter:
#     """
#     Abstract router for branch based endpoints.
#     """

#     def __init__(self, prefix="", staff_mode=False):
#         self.prefix = prefix
#         self.staff_mode = staff_mode

#     def register(self, route, view):
#         urls = []

#         base = f"{self.prefix}{route}/"

#         # Admin routes (can specify branch)
#         if not self.staff_mode:
#             urls += [
#                 path(base, view.as_view()),
#                 path(f"{self.prefix}<int:branch_id>/{route}/", view.as_view()),
#             ]

#         # Staff routes (branch auto detected)
#         else:
#             urls += [
#                 path(base, view.as_view()),
#             ]

#         return urls
