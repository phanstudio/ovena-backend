from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from menu.serializers import InS, OpS
from authflow.permissions import IsBusinessAdmin
from authflow.authentication import CustomBAdminAuth
# from storages.backends.s3boto3 import S3Boto3Storage # type: ignore
from ulid import ULID # type: ignore
from drf_spectacular.utils import extend_schema # type: ignore
from rest_framework.permissions import AllowAny
from django.core.files.storage import storages

# The images
# Logo images
# Display image
# CAC certification image

# might be a little harder than i thought

@extend_schema(
    responses=OpS.BatchGenerateUploadURLResponseSerializer
)
class BatchGenerateUploadURLBaseView(GenericAPIView): # add a check to make sure you are currenty on the 3 phase
    permission_classes = [AllowAny]
    serializer_class = InS.BatchGenerateUploadURLRequestSerializer

    ALLOWED_TYPES = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
    }
    MAX_SIZE_BYTES = 5 * 1024 * 1024
    MAX_BATCH = 150

    def get_files(self, data):
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data["files"]
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context.update({
            "max_batch": self.MAX_BATCH, 
            "max_size_bytes": self.MAX_SIZE_BYTES
        })
        return context

    def build_key(self, file_data, ext):
        return f"upload/{ULID()}.{ext}"
    
    def set_defaults(self, request):
        ...

    def post(self, request):
        files = self.get_files(request.data)

        self.set_defaults(request)
        # Use django-storages backend instead of raw boto3
        storage = storages["default"]
        s3_client = storage.connection.meta.client

        results = []
        for f in files:
            ext = self.ALLOWED_TYPES[f["content_type"]]
            key = self.build_key(f, ext)

            upload_url = s3_client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": storage.bucket_name,
                    "Key": key,
                    "ContentType": f["content_type"],
                    "ContentLength": int(f["file_size"]),
                },
                ExpiresIn=900,
            )

            results.append({
                "ref_id": f.get("ref_id"),
                "upload_url": upload_url,
                # uses your configured custom_domain automatically
                "public_url": storage.url(key),
                # "public_url": f"https://{storage.custom_domain}/{key}",
            })

        return Response({"urls": results})


class BatchGenerateBuisnessURLView(BatchGenerateUploadURLBaseView): # add a check to make sure you are currenty on the 3 phase
    authentication_classes = [CustomBAdminAuth]
    permission_classes = [IsBusinessAdmin]

    def set_defaults(self, request):
        self.business_id = request.user.business_admin.business_id
        return super().set_defaults(request)

    def build_key(self, file_data, ext):
        return (
            f"businesses/"
            f"{self.business_id}/"
            f"menu/"
            f"{ULID()}.{ext}"
        )

    # def post(self, request):
    #     files = self.get_files(request.data)

    #     business = request.user.business_admin.business
        
    #     # Use django-storages backend instead of raw boto3
    #     storage = storages["default"]
    #     s3_client = storage.connection.meta.client

    #     results = []
    #     for f in files:
    #         ext = self.ALLOWED_TYPES[f["content_type"]]
    #         key = f"businesses/{business.id}/menu/{ULID()}.{ext}"

    #         upload_url = s3_client.generate_presigned_url(
    #             "put_object",
    #             Params={
    #                 "Bucket": storage.bucket_name,
    #                 "Key": key,
    #                 "ContentType": f["content_type"],
    #                 "ContentLength": int(f["file_size"]),
    #             },
    #             ExpiresIn=900,
    #         )

    #         results.append({
    #             "ref_id": f.get("ref_id"),
    #             "upload_url": upload_url,
    #             # uses your configured custom_domain automatically
    #             "public_url": f"https://{storage.custom_domain}/{key}",
    #         })

    #     return Response({"urls": results})

