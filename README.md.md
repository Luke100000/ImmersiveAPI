# ImmersiveAPI

A diverse set of API endpoints for various projects to avoid overhead introduced by creating new repos, deployments, etc.

## Structure

* `modules` - Each directory represents a module and contains at least a `.py` with the same name, containing a methode `init(app: FastAPI, config: DynaBox)`
* `common` - Shared code between modules
* `cache` - Persistent cache for data, each module should have its own subdirectory
* `temp` - Temporary files, each module should clean up after the task is done
* `data` - Static data
* `config.toml` / `default_config.toml` - Used to toggle modules and pass additional config

## Module

Each module is a group of **self-contained, async, threadsafe** endpoints.

````py
# todo
````

## Heavy lifting

For heavy work, use the worker process pool.

```py
# todo
```