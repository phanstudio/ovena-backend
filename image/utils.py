from django.db.models.fields.files import ImageFieldFile

def get_image(image):
    if isinstance(image, ImageFieldFile):
        return image.url if image else None

    if isinstance(image, str):
        return image

    return image