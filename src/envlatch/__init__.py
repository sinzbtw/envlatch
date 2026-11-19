"""Validate environment files against a contract without exposing their values."""

__version__ = "0.8.0"

from .comparison import ComparisonReport, compare
from .core import Issue, Report, check

__all__ = ["Issue", "Report", "check", "ComparisonReport", "compare", "__version__"]
