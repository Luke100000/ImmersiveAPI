# ImmersiveAPI

A diverse set of API endpoints for various projects to avoid overhead introduced by creating new repos, deployments,
etc.

## Structure

* `src/modules` - Each directory represents a module and contains at least a `.py` with the same name, containing the
  initializer.
* `cache` - Persistent cache for data, each module should have its own subdirectory.
* `temp` - Temporary files, each module should clean up after the task is done.
* `data` - Static data.
* `data/config.toml` / `data/default_config.toml` - Used to toggle modules and pass additional config.

## Module

Each module is a group of **self-contained, thread safe** endpoints.

````py
from ...configurator import Configurator


def init(configurator: Configurator):
    configurator.register("Name", "Description")

    @configurator.post("/v1/your_module/your_endpoint")
    async def your_endpoint():
        return {"hello": "world"}
````

## Heavy lifting

For heavy background work, use the worker process pool.

Either use the primary executor, shared among all endpoints:

```py
from worker import get_primary_executor


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
from worker import Executor

executor = Executor(1)
```

## Not process-safe

Do not launch with multiple workers, not all operations are process-safe, and especially the ML endpoints would blow up in memory.
Use (background) workers instead.