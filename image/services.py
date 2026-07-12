import logging
from django.core.files.storage import storages
from django.conf import settings

logger = logging.getLogger(__name__)

class S3StorageService:
    @staticmethod
    def get_storage():
        return storages["default"]

    # @classmethod
    # def delete_file_by_url(cls, public_url: str) -> bool:
    #     """
    #     Extracts the S3 object key path from a full public URL and deletes it.
    #     """
    #     if not public_url:
    #         return False
            
    #     storage = cls.get_storage()
    #     custom_domain = getattr(storage, "custom_domain", None) or settings.AWS_S3_CUSTOM_DOMAIN
        
    #     try:
    #         # Strip out the domain prefix to isolate the storage path/key
    #         prefix = f"https://{custom_domain}/"
    #         if public_url.startswith(prefix):
    #             key = public_url.replace(prefix, "")
    #         else:
    #             # Fallback check if it contains the bucket sub-root path
    #             key = public_url.split(f"{storage.bucket_name}/")[-1]
            
    #         print(storage.exists(key))
    #         if storage.exists(key):
    #             print("exist")
    #             storage.delete(key)
    #             return True
    #     except Exception as e:
    #         logger.error(f"S3 file deletion failed for URL {public_url}: {str(e)}")
            
    #     return False
    
    @classmethod
    def extract_key_from_url(cls, public_url: str) -> str:
        """Helper to safely parse out the S3 object key from a full URL string."""
        if not public_url or not isinstance(public_url, str):
            return ""
        storage = cls.get_storage()
        custom_domain = getattr(storage, "custom_domain", None) or settings.AWS_S3_CUSTOM_DOMAIN
        prefix = f"https://{custom_domain}/"
        
        if public_url.startswith(prefix):
            return public_url.replace(prefix, "")
        elif f"{storage.bucket_name}/" in public_url:
            return public_url.split(f"{storage.bucket_name}/")[-1]
        return public_url

    @classmethod
    def delete_file_by_url(cls, public_url: str) -> bool:
        if not public_url:
            return False
        storage = cls.get_storage()
        key = cls.extract_key_from_url(public_url)  # reuse the same helper
        if not key:
            return False
        try:
            s3_client = storage.connection.meta.client
            s3_client.delete_object(Bucket=storage.bucket_name, Key=key)
            return True
        except Exception as e:
            logger.error(f"[S3 image delete]: {str(e)}")
            return False


# class BulkS3StorageService:
#     @staticmethod
#     def get_storage():
#         return storages["default"]

#     @classmethod
#     def extract_key_from_url(cls, public_url: str) -> str:
#         """Helper to safely parse out the S3 object key from a full URL string."""
#         if not public_url or not isinstance(public_url, str):
#             return ""
#         storage = cls.get_storage()
#         custom_domain = getattr(storage, "custom_domain", None) or settings.AWS_S3_CUSTOM_DOMAIN
#         prefix = f"https://{custom_domain}/"
        
#         if public_url.startswith(prefix):
#             return public_url.replace(prefix, "")
#         elif f"{storage.bucket_name}/" in public_url:
#             return public_url.split(f"{storage.bucket_name}/")[-1]
#         return public_url

#     @classmethod
#     def batch_delete_urls(cls, url_list: list[str]) -> bool:
#         """
#         Deletes up to 1,000 S3 assets in a single network request.
#         """
#         # Filter out empty entries and extract the keys
#         keys_to_delete = [
#             {"Key": cls.extract_key_from_url(url)} 
#             for url in url_list if url
#         ]
        
#         if not keys_to_delete:
#             return False

#         storage = cls.get_storage()
#         s3_client = storage.connection.meta.client

#         try:
#             # Chunk into blocks of 1000 (AWS S3 MAX limit per call)
#             for i in range(0, len(keys_to_delete), 1000):
#                 chunk = keys_to_delete[i:i+1000]
#                 s3_client.delete_objects(
#                     Bucket=storage.bucket_name,
#                     Delete={"Objects": chunk, "Quiet": True}
#                 )
#             return True
#         except Exception as e:
#             logger.error(f"Failed to execute batch S3 deletion: {str(e)}")
#             return False


# ─────────────────────────────────────────────────────────────────────────────
# S3 bulk-delete service
# ─────────────────────────────────────────────────────────────────────────────

class BulkS3StorageService:
    @staticmethod
    def get_storage():
        return storages["default"]

    @classmethod
    def extract_key_from_url(cls, public_url: str) -> str:
        """Safely parse the S3 object key out of a full URL string."""
        if not public_url or not isinstance(public_url, str):
            return ""
        storage = cls.get_storage()
        custom_domain = getattr(storage, "custom_domain", None) or settings.AWS_S3_CUSTOM_DOMAIN
        prefix = f"https://{custom_domain}/"
        if public_url.startswith(prefix):
            return public_url.replace(prefix, "")
        elif f"{storage.bucket_name}/" in public_url:
            return public_url.split(f"{storage.bucket_name}/")[-1]
        return public_url

    @classmethod
    def batch_delete_urls(cls, url_list: list[str]) -> bool:
        """
        Deletes S3 assets in chunks of 1,000 (AWS hard limit per call).
        Returns False if there is nothing to delete or the call fails.
        """
        keys_to_delete = [
            {"Key": cls.extract_key_from_url(url)}
            for url in url_list if url
        ]
        if not keys_to_delete:
            return False

        storage = cls.get_storage()
        s3_client = storage.connection.meta.client
        try:
            for i in range(0, len(keys_to_delete), 1000):
                chunk = keys_to_delete[i:i + 1000]
                s3_client.delete_objects(
                    Bucket=storage.bucket_name,
                    Delete={"Objects": chunk, "Quiet": True},
                )
            return True
        except Exception as e:
            logger.error(f"Failed to execute batch S3 deletion: {str(e)}")
            return False
