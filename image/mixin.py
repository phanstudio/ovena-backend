# from rest_framework.response import Response
# from rest_framework import status
from .services import S3StorageService, BulkS3StorageService

class S3ImageManagedMixin:
    """
    Mixin containing helper utilities to modify or clear field-backed 
    S3 assets on an object instance.
    """
    
    def update_image_field(self, instance, field_name: str, new_image: str, save= True):
        """
        Safely replaces an existing image URL with a new path, cleaning up S3.
        """
        old_image = getattr(instance, field_name, None)
        
        # If the URL is changing, purge the legacy media from S3
        if old_image.url:# and old_image.url != new_image:
            S3StorageService.delete_file_by_url(old_image.url)
            
        setattr(instance, field_name, new_image)
        if save:
            instance.save(update_fields=[field_name])

    def delete_image_field(self, instance, field_name: str, save= True):
        """
        Removes an image string pointer from a model field and purges it from S3.
        """
        old_image = getattr(instance, field_name, None)
        if old_image.url:
            S3StorageService.delete_file_by_url(old_image.url)
            
        setattr(instance, field_name, None)
        if hasattr(instance, "save") and save:
            instance.save(update_fields=[field_name])
            
        # return Response(
        #     {"detail": f"Asset attached to '{field_name}' successfully removed."}, 
        #     status=status.HTTP_204_NO_CONTENT
        # )


class BuilkS3ImageManagedMixin:
    """
    Mixin containing helper utilities to modify or clear field-backed 
    S3 assets on an object instance.
    """
    
    def update_image_field(self, instance, image_dict: dict[str, str], save= True):
        """
        Safely replaces an existing image URL with a new path, cleaning up S3.
        """
         
        old_urls = []
        for field_name in image_dict.keys():
            old_image = getattr(instance, field_name, None)
            if old_image.url:
                old_urls.append(old_image.url)
        
        # If the URL is changing, purge the legacy media from S3
        if old_urls:# and old_image.url != new_image:
            BulkS3StorageService.batch_delete_urls(old_urls)
        
        for field_name, new_image in image_dict.items():
            setattr(instance, field_name, new_image)
        if save:
            instance.save(update_fields=list(image_dict.keys()))

    def delete_image_field(self, instance, field_names: list[str], save= True):
        """
        Removes an image string pointer from a model field and purges it from S3.
        """
        old_urls = []
        for field_name in field_names:
            old_image = getattr(instance, field_name, None)
            if old_image.url:
                old_urls.append(old_image.url)
        
        if old_urls:
            BulkS3StorageService.batch_delete_urls(old_urls)
        
        for field_name in field_names:
            setattr(instance, field_name, None)
        if hasattr(instance, "save") and save:
            instance.save(update_fields=field_names)
            
        # return Response(
        #     {"detail": f"Asset attached to '{field_name}' successfully removed."}, 
        #     status=status.HTTP_204_NO_CONTENT
        # )

