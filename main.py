from dotenv import load_dotenv

load_dotenv()

import os
import shutil

from prometheus_client import CollectorRegistry, multiprocess
from starlette.middleware.gzip import GZipMiddleware

from modules.converter.converterModule import initConverterModule
from modules.patreon.patreonModule import initPatreon

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

# Prometheus integration
instrumentator = Instrumentator().instrument(app)

# Enable modules
initConverterModule(app)
initPatreon(app)


@app.on_event("startup")
async def startup():
    instrumentator.expose(app)
