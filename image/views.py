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
from business_api.views import BaseBuisAdminAPIView
from rest_framework.parsers import MultiPartParser, FormParser
from django.db import transaction
from rest_framework import status
# from PIL import Image


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
                "public_url": f"https://{storage.custom_domain}/{key}",#storage.url(key),
                # CLOUD_PUBLIC_CUSTOM_DOMAIN
                
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


class UpdateBusinessImagesView(BaseBuisAdminAPIView):

    parser_classes = [MultiPartParser, FormParser]
    MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB

    ALLOWED_TYPES = {
        "image/jpeg",
        "image/png",
        "image/webp",
    }

    def validate_image(self, file):
        # Check content type
        if file.content_type not in self.ALLOWED_TYPES:
            raise ValueError(
                "Only JPEG, PNG, and WEBP images are allowed."
            )

        # Check file size
        if file.size > self.MAX_IMAGE_SIZE:
            raise ValueError(
                "Image size cannot exceed 5MB."
            )

        # # Verify actual image
        # try:
        #     img = Image.open(file)
        #     img.verify()
        # except Exception:
        #     raise ValueError(
        #         "Invalid or corrupted image."
        #     )

        # # Reset file pointer after verify()
        # file.seek(0)

    def patch(self, request):
        business_admin = self.get_buisnessadmn(request)
        restaurant = business_admin.business

        business_image = request.FILES.get("business_image")
        business_logo = request.FILES.get("business_logo")

        if not business_image and not business_logo:
            return Response(
                {
                    "detail":
                    "At least one image must be uploaded."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():

                # BUSINESS IMAGE
                if business_image:
                    self.validate_image(business_image)
                    restaurant.business_image = business_image

                # BUSINESS LOGO
                if business_logo:
                    self.validate_image(business_logo)
                    restaurant.business_logo = business_logo

                restaurant.save(
                    update_fields=[
                        "business_image",
                        "business_logo",
                    ]
                )

            return Response(
                {"detail": "Images updated successfully."},
                status=status.HTTP_200_OK,
            )

        except ValueError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception:
            return Response(
                {"detail": "Failed to upload images."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

