"""Exceptions for the Configuration subsystem (GET/PUT /config, per-run
overrides at POST /runs and POST /runs/{id}/rerun). Kept separate from
service.py so app.api.config, app.api.runs, and app.orchestration.rerun
can import just the error types without pulling in the DB-touching
service functions.
"""


class UnknownConfigKeyError(Exception):
    """Raised when a per-run/rerun config_overrides entry, or a PUT
    /config/{id} target, names a key that doesn't match any entry in
    app.configuration.catalog.CATALOG."""

    def __init__(self, key: str):
        self.key = key
        super().__init__(
            f"'{key}' is not a known configuration key. See GET /config for the "
            f"full list of valid keys."
        )


class ConfigValueOutOfBoundsError(Exception):
    """Raised when a proposed value falls outside a catalog entry's own
    documented, sane bounds (e.g. a proportion outside [0, 1])."""

    def __init__(self, key: str, value: float, low, high):
        self.key = key
        self.value = value
        self.low = low
        self.high = high
        bound_desc = (
            f"[{low if low is not None else '-inf'}, {high if high is not None else '+inf'}]"
        )
        super().__init__(
            f"Value {value} for '{key}' is outside its valid range {bound_desc}."
        )


class ConfigNotFoundError(Exception):
    """Raised when PUT /config/{id} names a config row that doesn't exist."""

    def __init__(self, config_id: str):
        self.config_id = config_id
        super().__init__(f"Config threshold '{config_id}' not found.")
