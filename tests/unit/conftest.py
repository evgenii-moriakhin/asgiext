from __future__ import annotations

import pytest

from asgiext.features.core.asgi_web_server import ASGIWebServerConfig, ASGIWebServerFeature


@pytest.fixture()
def asgi_web_server_feature() -> ASGIWebServerFeature:
    """Stub for use ASGIWebServerFeature in unit tests.

    Feature must often be present to initialize a test application, but its specific settings are not important
    """
    return ASGIWebServerFeature(
        config=ASGIWebServerConfig(type="hypercorn", config={"application_path": "it_does_not_matter_to_us.py"})
    )
