"""Validate environment files against a contract without exposing their values."""

__version__ = "0.7.0"

from .compare import ComparisonReport, compare
from .core import Issue, Report, check

__all__ = ["Issue", "Report", "check", "ComparisonReport", "compare", "__version__"]
