"""sfdigest: read-only digest of Salesforce setup changes."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("sfdigest")
except PackageNotFoundError:  # running from a source tree without install
    __version__ = "0.0.0"
