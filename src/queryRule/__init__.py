from .base import QueryRule
from .azure import AzureQueryRule
from .google import GoogleQueryRule

__all__ = ["QueryRule", "AzureQueryRule", "GoogleQueryRule"]
