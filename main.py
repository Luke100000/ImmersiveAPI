from typing import Callable

from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware

load_dotenv()

import time
import os
import shutil

from prometheus_client import CollectorRegistry, multiprocess
from starlette.middleware.gzip import GZipMiddleware

from modules.itchio.itchioModule import itchioModule
from modules.converter.converterModule import initConverterModule
from modules.patreon.patreonModule import initPatreon
from modules.hagrid.hagrid import initHagrid
from modules.phrasey.phrases import initPhrasey

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


def benchmark(initializer: Callable, *args, **kwargs):
    start = time.time()
    initializer(*args, **kwargs)
    end = time.time()
    print(f"Initialized {initializer.__name__} in {end - start:.2f}s")


# Enable modules
benchmark(initConverterModule, app)
benchmark(initPatreon, app)
benchmark(itchioModule, app)
benchmark(initHagrid, app)
benchmark(initPhrasey, app)


@app.on_event("startup")
async def startup():
    instrumentator.expose(app)
