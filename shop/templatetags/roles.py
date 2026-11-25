"""Presentation-only role checks, independent of authorization."""

from django import template
from shop.context_processors import role_names

register = template.Library()


@register.filter
def in_group(user, name):
    """Check cached group membership for presentation."""
    return name in role_names(user)
