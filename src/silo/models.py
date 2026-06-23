from dataclasses import dataclass, field, asdict
from typing import Any
import json

CONFIG_DEFAULTS: dict[str, Any] = {
    "name": "silo-user",
    "email": "user@silo.local",
    "frozen": False,
    "theme": "default",
    "use_gitignore": False,
}

CONFIG_SCHEMA: dict[str, type] = {
    "name": str,
    "email": str,
    "frozen": bool,
    "theme": str,
    "use_gitignore": bool,
}


@dataclass
class Commit:
    hash: str
    tree: dict[str, str]
    parent: str | None
    author: str
    message: str
    co_authors: list[str] = field(default_factory=list)
    timestamp: float = 0.0
    branch: str = "main"

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, s: str) -> "Commit":
        d: dict[str, Any] = json.loads(s)
        return cls(**d)


@dataclass
class Tag:
    name: str
    commits: list[str] = field(default_factory=list)
    branch: str = ""
    timestamp: float = 0.0

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, s: str) -> "Tag":
        d: dict[str, Any] = json.loads(s)
        return cls(**d)


@dataclass
class Note:
    hash: str
    text: str
    commits: list[str] = field(default_factory=list)
    branch: str = ""
    timestamp: float = 0.0

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, s: str) -> "Note":
        d: dict[str, Any] = json.loads(s)
        return cls(**d)


@dataclass
class Config:
    data: dict[str, Any] = field(default_factory=lambda: dict(CONFIG_DEFAULTS))

    def __post_init__(self) -> None:
        self.data = {**CONFIG_DEFAULTS, **self.data}

    def get(self, key: str, default: Any | None = None) -> Any | None:
        return self.data.get(key, default)

    def set(self, key: str, val: Any) -> None:
        if key in CONFIG_SCHEMA:
            if CONFIG_SCHEMA[key] is bool:
                if isinstance(val, str):
                    val: bool = val.lower() in ("true", "1", "yes")
                else:
                    val: bool = bool(val)
            else:
                val: str = str(val)
        self.data[key] = val

    @property
    def name(self) -> str:
        return str(self.data.get("name", CONFIG_DEFAULTS["name"]))

    @name.setter
    def name(self, val: str) -> None:
        self.set("name", val)

    @property
    def email(self) -> str:
        return str(self.data.get("email", CONFIG_DEFAULTS["email"]))

    @email.setter
    def email(self, val: str) -> None:
        self.set("email", val)

    @staticmethod
    def validate(data: dict[str, Any]) -> list[str]:
        issues: list[str] = []
        for k, v in data.items():
            if k not in CONFIG_SCHEMA:
                issues.append(f"unknown key '{k}'")
            else:
                expected: type = CONFIG_SCHEMA[k]
                if not isinstance(v, expected):
                    issues.append(f"'{k}' should be {expected.__name__}, got {type(v).__name__}")
        return issues
