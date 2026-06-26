# Isolates "what region is this request in" — swap the internals later
# (e.g. reverse-geocode lat/lng to a metro) without touching cache keys
# or sections.

DEFAULT_REGION = "default"

def resolve_region(request, user_point=None) -> str:
    """
    For now: region == country code on the customer's profile / business data.
    Cheap, stable, matches your existing Business.country field.
    """
    country = request.query_params.get("country")
    if country:
        return country.upper()

    profile = getattr(request, "customer_profile", None)
    if profile and getattr(profile, "country", None):
        return profile.country.upper()

    return DEFAULT_REGION