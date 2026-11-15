"""Save slots stored as JSON files.

* Writes are **atomic**: data goes to a temp file which is then renamed over the
  real one, so a crash mid-save can't leave a half-written (corrupt) save.
* Every file carries a format version so future releases can migrate old saves.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FORMAT_VERSION = 1
_SLOT_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class SaveError(Exception):
    pass


class SaveNotFound(SaveError):
    pass


class CorruptSave(SaveError):
    pass


class SaveManager:
    def __init__(self, directory: str | os.PathLike[str]):
        self.directory = Path(directory)

    def _path(self, slot: str | int) -> Path:
        name = str(slot)
        # Slot names become file names; refuse anything that could escape the folder.
        if not _SLOT_RE.match(name):
            raise SaveError(f"invalid slot name {name!r} (use letters, digits, - and _)")
        return self.directory / f"{name}.json"

    def save(self, slot: str | int, data: dict[str, Any], *, label: str = "") -> Path:
        path = self._path(slot)
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = {
            "format": FORMAT_VERSION,
            "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "label": label,
            "data": data,
        }
        fd, tmp = tempfile.mkstemp(dir=self.directory, prefix=".tmp_", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            os.replace(tmp, path)  # atomic on the same filesystem
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        return path

    def load(self, slot: str | int) -> dict[str, Any]:
        path = self._path(slot)
        if not path.exists():
            raise SaveNotFound(f"no save in slot {slot!r}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise CorruptSave(f"slot {slot!r} is not valid JSON: {exc}") from exc
        if not isinstance(payload, dict) or "data" not in payload:
            raise CorruptSave(f"slot {slot!r} is missing its data")
        if payload.get("format", 0) > FORMAT_VERSION:
            raise CorruptSave(f"slot {slot!r} was written by a newer version of Swyft")
        return payload["data"]

    def exists(self, slot: str | int) -> bool:
        return self._path(slot).exists()

    def delete(self, slot: str | int) -> None:
        path = self._path(slot)
        if path.exists():
            path.unlink()

    def list_slots(self) -> list[dict[str, Any]]:
        """Metadata for every readable slot, newest first."""
        found: list[dict[str, Any]] = []
        if not self.directory.exists():
            return found
        for path in self.directory.glob("*.json"):
            if path.name.startswith(".tmp_"):
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                found.append(
                    {"slot": path.stem, "saved_at": payload.get("saved_at", ""), "label": payload.get("label", "")}
                )
            except (json.JSONDecodeError, UnicodeDecodeError, OSError):
                continue
        return sorted(found, key=lambda m: m["saved_at"], reverse=True)
