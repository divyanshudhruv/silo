try:
    from importlib.metadata import version as _v
    __version__ = _v("silo")
except Exception:
    __version__ = "0.0.0"
