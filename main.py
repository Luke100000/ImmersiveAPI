from typing import Callable

from dotenv import load_dotenv
from dynaconf import Dynaconf
from starlette.middleware.cors import CORSMiddleware

from modules.hugging.worker import get_primary_executor

load_dotenv()

import time
import os
import shutil

from prometheus_client import CollectorRegistry, multiprocess
from starlette.middleware.gzip import GZipMiddleware

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

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI()

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

settings = Dynaconf(settings_files=["default_config.toml", "config.toml"])


def benchmark(initializer: Callable, *args, **kwargs):
    if settings[initializer.__name__[4:]].enable:
        start = time.time()
        initializer(*args, **kwargs)
        end = time.time()
        print(f"Initialized {initializer.__name__} in {end - start:.2f}s")


# Enable modules
if settings.Converter.enable:
    from modules.converter.converterModule import initConverter

    benchmark(initConverter, app)

if settings.Patreon.enable:
    from modules.patreon.patreonModule import initPatreon

    benchmark(initPatreon, app)

if settings.ItchIo.enable:
    from modules.itchio.itchio import initItchIo

    benchmark(initItchIo, app)

if settings.Hagrid.enable:
    from modules.hagrid.hagrid import initHagrid

    benchmark(initHagrid, app)

if settings.Phrasey.enable:
    from modules.phrasey.phrases import initPhrasey

    benchmark(initPhrasey, app)

if settings.Hugging.enable:
    from modules.hugging.hugging import initHugging

    benchmark(initHugging, app)

if settings.MCA.enable:
    from modules.mca.mca import initMCA

    benchmark(initMCA, app)

if settings.Error.enable:
    from modules.error.error import initError

    benchmark(initError, app)


@app.on_event("startup")
async def startup():
    instrumentator.expose(app)


@app.on_event("shutdown")
async def shutdown():
    get_primary_executor().shutdown()
