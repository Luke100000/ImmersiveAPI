from typing import Callable

from dotenv import load_dotenv
from dynaconf import Dynaconf
from starlette.middleware.cors import CORSMiddleware

load_dotenv()

import time
import os
import shutil

from prometheus_client import CollectorRegistry, multiprocess
from starlette.middleware.gzip import GZipMiddleware

from modules.itchio.itchioModule import initItchIo
from modules.converter.converterModule import initConverter
from modules.patreon.patreonModule import initPatreon
from modules.hagrid.hagrid import initHagrid
from modules.phrasey.phrases import initPhrasey
from modules.hugging.hugging import initHugging
from modules.youare.youare import initYouAre

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

settings = Dynaconf(settings_files=["config.toml", "default_config.toml"])


def benchmark(initializer: Callable, *args, **kwargs):
    print(initializer.__name__[4:])
    if settings[initializer.__name__[4:]].enable:
        start = time.time()
        initializer(*args, **kwargs)
        end = time.time()
        print(f"Initialized {initializer.__name__} in {end - start:.2f}s")


# Enable modules
benchmark(initConverter, app)
benchmark(initPatreon, app)
benchmark(initItchIo, app)
benchmark(initHagrid, app)
benchmark(initPhrasey, app)
benchmark(initHugging, app)
benchmark(initYouAre, app)


@app.on_event("startup")
async def startup():
    instrumentator.expose(app)
