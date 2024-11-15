import json
from typing import Optional

from cachetools import cached, TTLCache
from sqlalchemy import (
    create_engine,
    Integer,
    String,
    Text,
    update,
)
from sqlalchemy.orm import declarative_base, Mapped, mapped_column, sessionmaker

from modules.mc_version_stats.mod import Mod

Base = declarative_base()


class ModTable(Base):
    __tablename__ = "mods"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False)
    last_modified: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)

    name: Mapped[str] = mapped_column(String, nullable=False)
    author: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String)
    categories: Mapped[str] = mapped_column(String)

    downloads: Mapped[int] = mapped_column(Integer, default=0)
    follows: Mapped[int] = mapped_column(Integer, default=0)

    body: Mapped[str] = mapped_column(Text)
    license: Mapped[str] = mapped_column(String)
    links: Mapped[str] = mapped_column(Text)
    icon: Mapped[str] = mapped_column(String)
    gallery: Mapped[str] = mapped_column(Text)

    mod_loaders: Mapped[str] = mapped_column(String, default="")
    versions: Mapped[str] = mapped_column(Text, default="")

    def to_mod(self):
        return Mod(
            id=self.id,
            source=self.source,
            slug=self.slug,
            last_modified=self.last_modified,
            created_at=self.created_at,
            name=self.name,
            author=self.author,
            description=self.description,
            type=self.type,
            categories=set(self.categories.split(",")),
            downloads=self.downloads,
            follows=self.follows,
            body=self.body,
            license=self.license,
            links=json.loads(self.links),
            icon=self.icon,
            gallery=json.loads(self.gallery),
            mod_loaders=set(self.mod_loaders.split(",")),
            versions=self.versions.split(","),
        )


def from_mod(mod: Mod):
    return ModTable(
        id=mod.id,
        source=mod.source,
        slug=mod.slug,
        last_modified=mod.last_modified,
        created_at=mod.created_at,
        name=mod.name,
        author=mod.author,
        description=mod.description,
        type=mod.type,
        categories=",".join(mod.categories),
        downloads=mod.downloads,
        follows=mod.follows,
        body=mod.body,
        license=mod.license,
        links=json.dumps(mod.links),
        icon=mod.icon,
        gallery=json.dumps(mod.gallery),
        mod_loaders=",".join(mod.mod_loaders),
        versions=",".join(mod.versions),
    )


class ModDatabase:
    def __init__(self, db_url: str = "sqlite:///cache/mods.sqlite"):
        self.engine = create_engine(db_url, echo=False)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def add_mod(self, mod: Mod) -> None:
        with self.Session() as session:
            mod_instance = from_mod(mod)
            session.merge(mod_instance)
            session.commit()

    def update_mod(self, mod: Mod) -> None:
        with self.Session() as session:
            mod_instance = from_mod(mod)
            session.execute(
                update(ModTable)
                .where(ModTable.id.__eq__(mod.id))
                .values(
                    slug=mod_instance.slug,
                    last_modified=mod_instance.last_modified,
                    name=mod_instance.name,
                    author=mod.author,
                    description=mod_instance.description,
                    categories=mod_instance.categories,
                    downloads=mod_instance.downloads,
                    follows=mod_instance.follows,
                    license=mod_instance.license,
                    icon=mod_instance.icon,
                )
            )

    def get_mod(self, mod_id: str) -> Optional[Mod]:
        with self.Session() as session:
            mod: Optional[ModTable] = (
                session.query(ModTable).filter_by(id=mod_id).first()
            )
            return None if mod is None else mod.to_mod()

    @cached(TTLCache(maxsize=1, ttl=3600))
    def get_mods(self):
        with self.Session() as session:
            # noinspection PyTypeChecker
            mods: list[ModTable] = session.query(ModTable).all()
            return [mod.to_mod() for mod in mods]
