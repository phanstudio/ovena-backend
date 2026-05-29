from rest_framework.pagination import PageNumberPagination, LimitOffsetPagination

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20                   # default page size
    page_size_query_param = "page_size"
    max_page_size = 100

class StandardLimitOffsetPagination(LimitOffsetPagination):
    default_limit = 20
    max_limit = 100