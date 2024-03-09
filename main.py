import glob
import importlib
import os
import shutil
import time

from dotenv import load_dotenv
from dynaconf import Dynaconf
from fastapi import FastAPI
from prometheus_client import CollectorRegistry, multiprocess
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

from common.worker import get_primary_executor

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


def start_module(name: str):
    start_import = time.time()
    module = importlib.import_module(f"modules.{name}.{name}")
    initializer = getattr(module, "init")

    start_init = time.time()
    kwargs = {"config": settings[name]}
    filtered_kwargs = {key: value for key, value in kwargs.items() if key in initializer.__code__.co_varnames}
    initializer(app, **filtered_kwargs)
    end = time.time()
    print(f"Initialized {name} in {end - start_import:.2f}s ({end - start_init:.2f}s initializing)")


def start_all_modules():
    for module in glob.glob("modules/*"):
        name = module[8:]
        if name in settings and settings[name].enable:
            start_module(name)
        else:
            print("Skipping", name)


@app.on_event("startup")
async def startup():
    instrumentator.expose(app)
    start_all_modules()


@app.on_event("shutdown")
async def shutdown():
    get_primary_executor().shutdown()
