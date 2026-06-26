from .implementations import (
    BannerSection, CarouselSection, FeaturedSection,
    TopPickSection, RecentlyViewedSection,
)

# Order here = order in the API response. Add/remove a line to
# add/remove a homepage block — nothing else changes.
HOME_SECTIONS = [
    BannerSection(),
    CarouselSection(),
    FeaturedSection(),
    TopPickSection(),
    RecentlyViewedSection(),
]