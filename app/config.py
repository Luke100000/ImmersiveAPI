from dynaconf import Dynaconf

from app.utils import get_data_path

# Load config
settings = Dynaconf(
    settings_files=[
        "default_config.toml",
        get_data_path("config.toml"),
    ]
)

print("Config", settings.as_dict())
