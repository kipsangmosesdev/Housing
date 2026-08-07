# myApp/templatetags/custom_filters.py
from django import template

register = template.Library()

@register.filter
def intersection(value, arg):
    """Returns the intersection of two lists"""
    return [item for item in value if item in arg]
