from rest_framework import serializers
from .models import (
    DriverRating,
    BranchRating,
    DriverComplaintType,
    BranchComplaintType,
)


# class DriverRatingSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = DriverRating
#         fields = [
#             "id",
#             "order",
#             "rater",
#             "driver",
#             "stars",
#             "complaint_type",
#             "review",
#             "created_at",
#         ]
#         read_only_fields = ["id", "created_at", "rater", "driver"]

#     def validate_complaint_type(self, value):
#         if value is None or value == "":
#             return None
#         valid = {c[0] for c in DriverComplaintType.choices}
#         if value not in valid:
#             raise serializers.ValidationError("Invalid driver complaint type.")
#         return value


# class BranchRatingSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = BranchRating
#         fields = [
#             "id",
#             "order",
#             "rater",
#             "branch",
#             "stars",
#             "complaint_type",
#             "review",
#             "created_at",
#         ]
#         read_only_fields = ["id", "created_at", "rater", "branch"]

#     def validate_complaint_type(self, value):
#         if value is None or value == "":
#             return None
#         valid = {c[0] for c in BranchComplaintType.choices}
#         if value not in valid:
#             raise serializers.ValidationError("Invalid branch complaint type.")
#         return value


# class SubmitOrderRatingsSerializer(serializers.Serializer):
#     """
#     One request that can submit either or both.
#     """
#     order_id = serializers.IntegerField()

#     driver = serializers.DictField(required=False)
#     branch = serializers.DictField(required=False)

#     def validate(self, attrs):
#         if "driver" not in attrs and "branch" not in attrs:
#             raise serializers.ValidationError("You must submit at least driver or branch rating.")

#         # Validate nested payloads lightly here; model will validate deeply too.
#         for key in ("driver", "branch"):
#             if key in attrs:
#                 payload = attrs[key]
#                 if "stars" not in payload:
#                     raise serializers.ValidationError({key: "stars is required"})
#                 stars = payload["stars"]
#                 if not (1 <= int(stars) <= 5):
#                     raise serializers.ValidationError({key: "stars must be 1..5"})

#         return attrs





# ratings/serializers.py
from rest_framework import serializers
from .models import DriverRating, BranchRating, DriverComplaintType, BranchComplaintType


class DriverRatingWriteSerializer(serializers.Serializer):
    stars = serializers.IntegerField(min_value=1, max_value=5)
    complaint_type = serializers.ChoiceField(
        choices=DriverComplaintType.choices, required=False, allow_null=True
    )
    review = serializers.CharField(required=False, allow_blank=True)


class BranchRatingWriteSerializer(serializers.Serializer):
    stars = serializers.IntegerField(min_value=1, max_value=5)
    complaint_type = serializers.ChoiceField(
        choices=BranchComplaintType.choices, required=False, allow_null=True
    )
    review = serializers.CharField(required=False, allow_blank=True)


class SubmitOrderRatingsSerializer(serializers.Serializer):
    order_id = serializers.IntegerField()
    driver = DriverRatingWriteSerializer(required=False)
    branch = BranchRatingWriteSerializer(required=False)

    def validate(self, attrs):
        if "driver" not in attrs and "branch" not in attrs:
            raise serializers.ValidationError("Submit at least a driver or branch rating.")
        return attrs


class DriverRatingReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = DriverRating
        fields = ["id", "order", "rater", "driver", "stars", "complaint_type", "review", "created_at"]


class BranchRatingReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = BranchRating
        fields = ["id", "order", "rater", "branch", "stars", "complaint_type", "review", "created_at"]
