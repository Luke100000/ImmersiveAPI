from dynaconf import Dynaconf

# Load config
settings = Dynaconf(settings_files=["default_config.toml", "config.toml"])
