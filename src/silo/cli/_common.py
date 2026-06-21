from ..utils import find_silo_dir
from ..theme import err


def require_silo():
    silo_dir = find_silo_dir()
    if not silo_dir:
        err("not a silo repository")
    return silo_dir
