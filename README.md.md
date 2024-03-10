# ImmersiveAPI

A diverse set of API endpoints for various projects to avoid overhead introduced by creating new repos, deployments,
etc.

## Launch

Use the launcher, which will start n workers and an additional worker for non-thread-safe endpoints.

If workers is one it will only launch a single worker.

```sh
launch.sh --workers 4 --port 8000 --secondary-port 8001
```

## Structure

* `modules` - Each directory represents a module and contains at least a `.py` with the same name, containing the
  initializer.
* `common` - Shared code between modules
* `cache` - Persistent cache for data, each module should have its own subdirectory
* `temp` - Temporary files, each module should clean up after the task is done
* `data` - Static data
* `config.toml` / `default_config.toml` - Used to toggle modules and pass additional config

## Module

Each module is a group of **self-contained, async, thread safe** endpoints.

````py
from main import Configurator


def init(configurator: Configurator):
    configurator.register("Name", "Description")

    @configurator.post("/v1/your_module/your_endpoint")
    async def your_endpoint():
        return {"hello": "world"}
````

## Heavy lifting

For heavy, background work, use the worker process pool.

Either use the primary executor, shared among all endpoints:

```py
from common.worker import get_primary_executor


def generate_text():
    return "Hello, world!"


async def your_endpoint():
    # noinspection PyUnusedLocal
    result = await get_primary_executor().submit(
        0,  # priority
        generate_text,
        # args...
        # kwargs...
    )
```

Or create a private executor for your module:

```py
from common.worker import Executor

executor = Executor(1)
```

## Not thread-safe

If your code is not thread-safe, not state-less, or is memory intensive and shall not make use of multiprocessing, mark
it as such.
It will then redirect to a single-threaded executor.

```py
from main import Configurator


def init(configurator: Configurator):
    # For the entire module
    configurator.set_non_thread_safe()

    # Or for specific endpoints only
    @configurator.post("/v1/your_module/your_endpoint", thread_safe=False)
    async def your_endpoint():
        pass
```