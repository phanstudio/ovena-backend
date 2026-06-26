BANNER = "banner"
TOP3_FEATURE_CODE = "top-3"
HIGH_RANK_FEATURE_CODE = "high-rank"
CAROUSEL = "carousel"
PRIORITY_SEARCH = "priority-search"
ADD_VISIBILITY = "add-visibility-search"
# priority-search
# add-visibility-search

ON_BANNER = [BANNER] # create banner, update banner
ON_CAROUSEL = [CAROUSEL] # create banner, update banner
# TOP3_FEATURE = [TOP3_FEATURE_CODE]
# HIGH_RANK_FEATURE = [HIGH_RANK_FEATURE_CODE]
# ON_PRIORITY_SEARCH = [PRIORITY_SEARCH]
# ON_ADD_VISIBILITY = [ADD_VISIBILITY]

HIGH_RANK_BOOST = 50  # tune so it reliably outranks organic scores
ADD_VISIBILITY_KM_BOOST = 2.0

# high ranking in the listing ✅
# increased visibility in search ✅

# top placement in category (not implemted)
# featured badge (explained)
# priority in search result ✅

# top 3 placement in listings ✅
# push notifications to users (not implemted)
# home page banner (second placement) ✅

# featured in homepage carousel ✅
# high click through visibility?? (not sure)
# limited 5-3 slots ()
# +premiums values


# seperate this into access and accessed level subscriptions??
# so we need a list of the people in a subscription perticulary for this people we need to store them in a cache; 
# we generate this lost from plan / subscriptions and we update this list from when cancle and subscripibe are called respectiveily.
# also when grace periods etc

# cache

# if this is true then:
# the tiers cacade;
# plus; priotiy for simular features