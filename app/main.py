import asyncio
import importlib
import logging
import os
import shutil
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from prometheus_client import CollectorRegistry, multiprocess
from prometheus_fastapi_instrumentator import Instrumentator
from redis.asyncio.client import Redis

from .config import settings
from .configurator import Configurator, tags_metadata
from .worker import Executor, get_primary_executor, set_primary_executor

load_dotenv()

logging.basicConfig()
logging.getLogger().setLevel(os.getenv("LOG_LEVEL", "INFO"))

# Setup prometheus for multiprocessing
prom_dir = (
    os.environ["PROMETHEUS_MULTIPROC_DIR"]
    if "PROMETHEUS_MULTIPROC_DIR" in os.environ
    else None
)
if prom_dir is not None:
    shutil.rmtree(prom_dir, ignore_errors=True)
    os.makedirs(prom_dir, exist_ok=True)
    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry)


app = FastAPI()


# Enable GZip compression
app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=6)


# Allow CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus integration
instrumentator = Instrumentator().instrument(app)


# Launch the background worker
set_primary_executor(Executor(settings["global"]["background_workers"]))


def start_module(name: str):
    print(f"Initializing {name}...")

    start_import = time.time()
    module = importlib.import_module(f"app.modules.{name}.{name}")
    initializer = getattr(module, "init")

    start_init = time.time()
    initializer(Configurator(app, settings[name]))
    end = time.time()

    print(
        f"Initialized {name} in {end - start_import:.2f}s ({end - start_init:.2f}s spent initializing)"
    )


def start_all_modules():
    modules_path = Path(__file__).parent / "modules"
    for module in modules_path.iterdir():
        if not module.is_dir():
            continue
        name = module.name
        if name in settings and getattr(settings[name], "enable", False):
            start_module(name)
        else:
            print("Skipping", name)


# Custom OpenAPI to fix the missing description
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title="Immersive API",
        version="0.0.1",
        description="Various APIs in one place",
        routes=app.routes,
    )

    openapi_schema["tags"] = tags_metadata

    app.openapi_schema = openapi_schema

    return app.openapi_schema


app.openapi = custom_openapi


@app.on_event("startup")
async def startup():
    FastAPICache.init(
        RedisBackend(
            Redis(
                host=os.getenv("REDIS_HOST", "localhost"),
                port=int(os.getenv("REDIS_PORT", "6379")),
            )
        ),
        prefix="api",
    )

    instrumentator.expose(app)
    start_all_modules()

    # Enable asyncio debugging
    if settings["global"]["asyncio_debug"]:
        asyncio.get_event_loop().set_debug(True)


@app.on_event("shutdown")
async def shutdown():
    get_primary_executor().shutdown()
