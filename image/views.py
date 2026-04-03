from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from menu.serializers import InS, OpS
from authflow.permissions import IsBusinessAdmin
from authflow.authentication import CustomBAdminAuth
from storages.backends.s3boto3 import S3Boto3Storage # type: ignore
from ulid import ULID # type: ignore
from drf_spectacular.utils import extend_schema # type: ignore

# The images
# Logo images
# Display image
# CAC certification image

# might be a little harder than i thought

@extend_schema(
    responses=OpS.BatchGenerateUploadURLResponseSerializer
)
class BatchGenerateUploadURLView(GenericAPIView): # add a check to make sure you are currenty on the 3 phase
    authentication_classes = [CustomBAdminAuth]
    permission_classes = [IsBusinessAdmin]
    serializer_class = InS.BatchGenerateUploadURLRequestSerializer

    ALLOWED_TYPES = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
    }
    MAX_SIZE_BYTES = 5 * 1024 * 1024
    MAX_BATCH = 150

    def post(self, request):
        files = request.data.get("files", [])

        if not files:
            return Response({"detail": "No files provided."}, status=400)
        if len(files) > self.MAX_BATCH:
            return Response({"detail": f"Max {self.MAX_BATCH} files per batch."}, status=400)

        for f in files:
            if f.get("content_type") not in self.ALLOWED_TYPES:
                return Response({"detail": f"Unsupported type: {f.get('content_type')}"}, status=400)
            if not f.get("file_size") or int(f["file_size"]) > self.MAX_SIZE_BYTES:
                return Response({"detail": "A file exceeds the 5MB limit."}, status=400)

        business = request.user.business_admin.business
        
        # Use django-storages backend instead of raw boto3
        storage = S3Boto3Storage()
        s3_client = storage.connection.meta.client

        results = []
        for f in files:
            ext = self.ALLOWED_TYPES[f["content_type"]]
            key = f"businesses/{business.id}/menu/{ULID()}.{ext}"

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
                "public_url": f"https://{storage.custom_domain}/{key}",
            })

        return Response({"urls": results})
