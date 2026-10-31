"""Separate experimental datasets without overwriting the original benchmark."""

import re
from pathlib import Path


def dataset_path(config, area, filename):
    if area not in {"interim", "processed", "reports"}:
        raise ValueError("Unknown artifact area")
    name = config.get("dataset")
    if name is not None and (not isinstance(name, str) or not re.fullmatch(r"[a-z0-9_]+", name)):
        raise ValueError("Dataset name must contain lowercase letters, digits and underscores")
    base = Path("reports") if area == "reports" else Path("data") / area
    return (base / name if name else base) / filename


def prepare_dataset(config):
    for area in ("interim", "processed", "reports"):
        dataset_path(config, area, "placeholder").parent.mkdir(parents=True, exist_ok=True)
