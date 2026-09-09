"""backend -- the FastAPI service that drives the coupled simulation.

Holds no ecology. Its job is to turn a scenario description into an
`ecocore.Grid`, run it off the request thread, and serve progress and results to
the browser.
"""

from .app import app, create_app
from .runner import JobStore

__all__ = ["JobStore", "app", "create_app"]
