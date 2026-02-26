from rest_framework.throttling import AnonRateThrottle


class PublicCatalogAnonThrottle(AnonRateThrottle):
    scope = "public_catalog"
