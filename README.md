# asgiext

WIP (This may never exist as a standalone library. It can be used simply as ideas and ready-made templates for creating ASGI web applications)

A Python library for building web applications with enhanced ASGI support.

## Features

- Provides a convenient set of abstractions over ASGI web servers (Uvicorn, Hypercorn) and frameworks (Starlette, Quart)
- Configurable logging (structlog), metrics, and more
- Extensible architecture using a feature-based concept


## Quick Start

1. Create an `app.py` file:

```python
from asgiext import init_app_and_get_runner
from asgiext.features.core.asgi_web_server import ASGIWebServerFeature
from asgiext.features.mongo import MongoFeature
from asgiext.features.app_features.starlette import StarletteFeature

starlette_feature = StarletteFeature()
features = [
    starlette_feature,
    ASGIWebServerFeature(),
    MongoFeature(),
]

runner = init_app_and_get_runner(features, starlette_feature)
app = starlette_feature.app
# Now you can add routes to your Starlette app
# app.add_route(...)
```

2. Create a `__main__.py` file:

```python
from app import runner

if __name__ == "__main__":
    runner()
```

3. Create a `config.yaml` file:

```yaml
ASGI_WEB_SERVER:
  type: uvicorn
  config:
    app: app:app
    host: 0.0.0.0

MONGO:
  host: localhost
  port: 27017
```

4. Run your application:

```bash
python -m your_app_name --conf config.yaml
```

## Creating Custom Features

You can create custom features by extending the AbstractApplicationFeature class:

```python
from asgiext.features.core import AbstractApplicationFeature, FeatureConfig


class MyFeatureConfig(FeatureConfig):
    # Define your feature's configuration here

class MyFeature(AbstractApplicationFeature[MyFeatureConfig]):
    name = "MY_FEATURE"

    def init(self) -> None:
        # Initialization code

    async def on_startup(self) -> None:
        # On server startup

    async def on_shutdown(self) -> None:
        # On server shutdown
```
