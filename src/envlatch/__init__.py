"""Validate environment files against a contract without exposing their values."""

__version__ = "0.6.1"

from .core import Issue, Report, check

__all__ = ["Issue", "Report", "check", "__version__"]
