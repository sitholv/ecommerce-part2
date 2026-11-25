"""Provide one cached role lookup for each rendered request."""


def role_names(user):
    """Cache group names on this request's user instance."""
    if not hasattr(user, "_market_role_names"):
        user._market_role_names = (
            set(user.groups.values_list("name", flat=True))
            if user.is_authenticated else set()
        )
    return user._market_role_names


def account_roles(request):
    """Return navigation flags without repeating group queries."""
    if not hasattr(request, "_market_roles"):
        request._market_roles = role_names(request.user)
    return {
        "is_buyer": "Buyers" in request._market_roles,
        "is_vendor": "Vendors" in request._market_roles,
    }
