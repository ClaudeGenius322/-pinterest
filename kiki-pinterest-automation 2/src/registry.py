"""Простой CSV-реестр для дедупликации фото между запусками."""
import csv
import hashlib
import os
from pathlib import Path
from typing import Set

FIELDNAMES = [
    "pin_id",
    "pin_url",
    "file_hash",
    "filename",
    "board_url",
    "yadisk_path",
    "yadisk_public_link",
    "downloaded_at",
]


class Registry:
    def __init__(self, path: str):
        self.path = Path(path)
        self._known_pin_ids: Set[str] = set()
        self._known_hashes: Set[str] = set()
        self._load()

    def _load(self):
        if not self.path.exists():
            return
        with open(self.path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("pin_id"):
                    self._known_pin_ids.add(row["pin_id"])
                if row.get("file_hash"):
                    self._known_hashes.add(row["file_hash"])

    def is_known(self, pin_id: str, file_hash: str = None) -> bool:
        if str(pin_id) in self._known_pin_ids:
            return True
        if file_hash and file_hash in self._known_hashes:
            return True
        return False

    def add(self, row: dict):
        is_new_file = not self.path.exists()
        with open(self.path, "a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            if is_new_file:
                writer.writeheader()
            writer.writerow(row)
        self._known_pin_ids.add(str(row.get("pin_id")))
        if row.get("file_hash"):
            self._known_hashes.add(row["file_hash"])


def file_md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
