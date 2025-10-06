from dynaconf import Dynaconf

# Load config
settings = Dynaconf(
    settings_files=[
        "default_config.toml",
        "data/default_config.toml",
        "/data/config.toml",
        "data/config.toml",
    ]
)
