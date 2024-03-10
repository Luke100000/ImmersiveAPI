import glob
import importlib
import os
import shutil
import sys
import time

from dotenv import load_dotenv
from dynaconf import Dynaconf
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from prometheus_client import CollectorRegistry, multiprocess
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

from common.redirect_middleware import PathRedirectMiddleware
from common.worker import get_primary_executor, set_primary_executor, Executor

load_dotenv()

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

# Check if this is a single process worker
is_single_process = "--workers 1" in (" ".join(sys.argv))

# If this is not a single process worker, we redirect non-thread-safe requests to the single process worker at port + 1
non_thread_safe_paths = set()
if not is_single_process:
    app.add_middleware(
        PathRedirectMiddleware,
        paths=non_thread_safe_paths,
        port=int(os.environ["SINGLE_PROCESS_WORKER_PORT"])
        if "SINGLE_PROCESS_WORKER_PORT" in os.environ
        else 8001,
    )

# Launch the background worker
set_primary_executor(
    Executor(settings["global"]["background_workers"] if is_single_process else 1)
)


class Configurator:
    def __init__(self, app_: FastAPI, config_: Dynaconf):
        self.tag = "default"
        self.app = app_
        self.config = config_

        self.thread_safe = True
        self.non_thread_safe = non_thread_safe_paths

    def is_single_process(self):
        return is_single_process

    def set_non_thread_safe(self):
        self.thread_safe = False

    def register(self, name: str, description: str):
        self.tag = name
        tags_metadata.append({"name": name, "description": description})

    def get(self, path, *args, thread_safe: bool = True, **kwargs):
        kwargs["tags"] = [self.tag]
        if not thread_safe or not self.thread_safe:
            self.non_thread_safe.add(path)
        return self.app.get(path, *args, **kwargs)

    def post(self, path, *args, thread_safe: bool = True, **kwargs):
        kwargs["tags"] = [self.tag]
        if not thread_safe or not self.thread_safe:
            self.non_thread_safe.add(path)
        return self.app.post(path, *args, **kwargs)

    def delete(self, path, *args, thread_safe: bool = True, **kwargs):
        kwargs["tags"] = [self.tag]
        if not thread_safe or not self.thread_safe:
            self.non_thread_safe.add(path)
        return self.app.delete(path, *args, **kwargs)

    def put(self, path, *args, thread_safe: bool = True, **kwargs):
        kwargs["tags"] = [self.tag]
        if not thread_safe or not self.thread_safe:
            self.non_thread_safe.add(path)
        return self.app.put(path, *args, **kwargs)


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
