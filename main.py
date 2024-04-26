import glob
import importlib
import logging
import os
import shutil
import time

from dotenv import load_dotenv
from dynaconf import Dynaconf
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from prometheus_client import CollectorRegistry, multiprocess
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

from common.worker import get_primary_executor, set_primary_executor, Executor

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

# Load config
settings = Dynaconf(settings_files=["default_config.toml", "config.toml"])

# Metadata for OpenAPI
tags_metadata = []

# Launch the background worker
set_primary_executor(Executor(settings["global"]["background_workers"]))


class Configurator:
    def __init__(self, app_: FastAPI, config_: Dynaconf):
        self.tag = "default"
        self.app = app_
        self.config = config_

    def assert_single_process(self):
        pass

    def register(self, name: str, description: str):
        self.tag = name
        tags_metadata.append({"name": name, "description": description})

    def get(self, *args, **kwargs):
        kwargs["tags"] = [self.tag]
        return self.app.get(*args, **kwargs)

    def post(self, *args, **kwargs):
        kwargs["tags"] = [self.tag]
        return self.app.post(*args, **kwargs)

    def delete(self, *args, **kwargs):
        kwargs["tags"] = [self.tag]
        return self.app.delete(*args, **kwargs)

    def put(self, *args, **kwargs):
        kwargs["tags"] = [self.tag]
        return self.app.put(*args, **kwargs)


def start_module(name: str):
    start_import = time.time()
    module = importlib.import_module(f"modules.{name}.{name}")
    initializer = getattr(module, "init")

    start_init = time.time()
    initializer(Configurator(app, settings[name]))
    end = time.time()
    print(
        f"Initialized {name} in {end - start_import:.2f}s ({end - start_init:.2f}s initializing)"
    )


def start_all_modules():
    for module in glob.glob("modules/*"):
        name = module[8:]
        if name in settings and settings[name].enable:
            start_module(name)
        else:
            print("Skipping", name)


# Custom OpenAPI to fix missing description
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
    instrumentator.expose(app)
    start_all_modules()


@app.on_event("shutdown")
async def shutdown():
    get_primary_executor().shutdown()
