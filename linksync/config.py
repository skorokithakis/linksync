import os
import tomllib
from dataclasses import dataclass


@dataclass(frozen=True)
class LinkoraConfig:
    url: str
    token: str
    verify_tls: bool


@dataclass(frozen=True)
class ReadeckConfig:
    url: str
    token: str


@dataclass(frozen=True)
class SyncConfig:
    state_db: str
    folder_name: str


@dataclass(frozen=True)
class Config:
    linkora: LinkoraConfig
    readeck: ReadeckConfig
    sync: SyncConfig


def load_config(path: str | None = None) -> Config:
    if path is None:
        path = "~/.config/linksync/config.toml"
    
    expanded_path = os.path.expanduser(path)
    
    with open(expanded_path, "rb") as file:
        data = tomllib.load(file)

    for section in ("linkora", "readeck", "sync"):
        if section not in data:
            raise SystemExit(f"Missing required config section: [{section}]")

    linkora_data = data["linkora"]
    readeck_data = data["readeck"]
    sync_data = data["sync"]

    for field in ("url", "token"):
        if field not in linkora_data:
            raise SystemExit(f"Missing required field: linkora.{field}")
        if field not in readeck_data:
            raise SystemExit(f"Missing required field: readeck.{field}")

    if "state_db" not in sync_data:
        raise SystemExit("Missing required field: sync.state_db")

    verify_tls = linkora_data.get("verify_tls", True)
    folder_name = sync_data.get("folder_name", "Read later")
    state_db = os.path.expanduser(sync_data["state_db"])
    
    linkora = LinkoraConfig(
        url=linkora_data["url"],
        token=linkora_data["token"],
        verify_tls=verify_tls,
    )
    
    readeck = ReadeckConfig(
        url=readeck_data["url"],
        token=readeck_data["token"],
    )
    
    sync = SyncConfig(
        state_db=state_db,
        folder_name=folder_name,
    )
    
    return Config(
        linkora=linkora,
        readeck=readeck,
        sync=sync,
    )
