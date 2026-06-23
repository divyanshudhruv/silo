from dataclasses import dataclass, field, asdict
from typing import Optional
import json


CONFIG_DEFAULTS = {
    "name": "silo-user",
    "email": "user@silo.local",
    "frozen": "false",
    "theme": "default",
    "use_gitignore": "false",
}

CONFIG_SCHEMA = {k: str for k in CONFIG_DEFAULTS}


@dataclass
class Commit:
    hash: str
    tree: dict
    parent: Optional[str]
    author: str
    message: str
    co_authors: list = field(default_factory=list)
    timestamp: float = 0.0
    branch: str = "main"

    def to_json(self):
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, s):
        d = json.loads(s)
        return cls(**d)


@dataclass
class Tag:
    name: str
    commits: list = field(default_factory=list)
    branch: str = ""
    timestamp: float = 0.0

    def to_json(self):
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, s):
        d = json.loads(s)
        return cls(**d)


@dataclass
class Note:
    hash: str
    text: str
    commits: list = field(default_factory=list)
    branch: str = ""
    timestamp: float = 0.0

    def to_json(self):
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, s):
        d = json.loads(s)
        return cls(**d)


@dataclass
class Config:
    data: dict = field(default_factory=lambda: dict(CONFIG_DEFAULTS))

    def __post_init__(self):
        self.data = {**CONFIG_DEFAULTS, **self.data}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, val):
        if key in CONFIG_SCHEMA:
            val = str(val)
        self.data[key] = val

    @staticmethod
    def validate(data):
        issues = []
        for k, v in data.items():
            if k not in CONFIG_SCHEMA:
                issues.append(f"unknown key '{k}'")
            else:
                expected = CONFIG_SCHEMA[k]
                if not isinstance(v, expected):
                    issues.append(f"'{k}' should be {expected.__name__}, got {type(v).__name__}")
        return issues
