class LocationMixin:
    def parse_point(self, point):
        if not point:
            return None

        return {
            "latitude": point.y,
            "longitude": point.x,
        }

class LocationFieldMixin(LocationMixin):
    location_field = "location"

    def get_point(self, obj):
        parts = self.location_field.split(".")
        value = obj
        for part in parts:
            value = getattr(value, part, None)
            if value is None:
                return None
        return value

    def get_location(self, obj):
        return self.parse_point(self.get_point(obj))
