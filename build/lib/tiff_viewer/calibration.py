"""Persistent manual spatial-calibration profiles."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Calibration:
    name: str
    micrometers_per_pixel: float

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Il profilo deve avere un nome")
        if self.micrometers_per_pixel <= 0:
            raise ValueError("La calibrazione deve essere maggiore di zero")

    def convert(self, pixels: float) -> float:
        return pixels * self.micrometers_per_pixel


class CalibrationStore:
    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            config_root = Path(
                os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
            )
            path = config_root / "tiff-viewer" / "calibrations.json"
        self.path = path

    def load(self) -> dict[str, Calibration]:
        if not self.path.exists():
            return {}
        try:
            content = json.loads(self.path.read_text(encoding="utf-8"))
            profiles = {}
            for item in content.get("profiles", []):
                profile = Calibration(
                    str(item["name"]),
                    float(item["micrometers_per_pixel"]),
                )
                profiles[profile.name] = profile
            return profiles
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return {}

    def save(self, profiles: dict[str, Calibration]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"profiles": [asdict(profile) for profile in profiles.values()]}
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        temporary.replace(self.path)

