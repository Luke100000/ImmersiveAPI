# ImmersiveAPI

A diverse set of API endpoints for various projects to avoid overhead introduced by creating new repos, deployments, etc.

## Structure

* `modules` - Each directory represents a module and contains at least a `.py` with the same name, containing the initializer.
* `common` - Shared code between modules
* `cache` - Persistent cache for data, each module should have its own subdirectory
* `temp` - Temporary files, each module should clean up after the task is done
* `data` - Static data
* `config.toml` / `default_config.toml` - Used to toggle modules and pass additional config

## Module

Each module is a group of **self-contained, async, threadsafe** endpoints.

````py
from main import Configurator

def init(configurator: Configurator):
    configurator.register("Name", "Description")

    @configurator.post("/v1/your_module/your_endpoint")
    async def your_endpoint():
        return {"hello": "world"}
````

## Heavy lifting

For heavy work, use the worker process pool.

```py
# Either use the primary executor, shared among all endpoints:
from common.worker import get_primary_executor

def generate_text():
    return "Hello, world!"

async def your_endpoint():
    result = await get_primary_executor().submit(
        0, # priority
        generate_text,
        # args...
        # kwargs...
    )

# Or create a private executor for your module:
from common.worker import Executor
executor = Executor(1)
```

## Not thread-safe
If your code is not thread-safe, assert so in your init function.

```py
from main import Configurator

def init(configurator: Configurator):
    configurator.assert_primary()
```