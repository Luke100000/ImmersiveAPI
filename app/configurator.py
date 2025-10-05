from dynaconf import Dynaconf
from fastapi import FastAPI

# Metadata for OpenAPI
tags_metadata = []


class Configurator:
    def __init__(self, app_: FastAPI, config_: Dynaconf):
        self.tag = "default"
        self.app = app_
        self.config = config_

    def register(self, name: str, description: str):
        self.tag = name
        tags_metadata.append({"name": name, "description": description})

    def get(self, *args, **kwargs):
        kwargs["tags"] = [self.tag]
        return self.app.get(*args, **kwargs)

    def post(self, *args, **kwargs):
        kwargs["tags"] = [self.tag]
        return self.app.post(*args, **kwargs)

    def delete(self, *args, **kwargs):
        kwargs["tags"] = [self.tag]
        return self.app.delete(*args, **kwargs)

    def put(self, *args, **kwargs):
        kwargs["tags"] = [self.tag]
        return self.app.put(*args, **kwargs)
