"""
Работа с Яндекс.Диском через REST API.
Документация: https://yandex.ru/dev/disk/api/reference/
"""
import os
import time
import requests

API_BASE = "https://cloud-api.yandex.net/v1/disk"


class YaDiskClient:
    def __init__(self, token: str):
        if not token:
            raise ValueError("Не задан YADISK_TOKEN")
        self.token = token
        self.headers = {"Authorization": f"OAuth {token}"}

    def resolve_public_path(self, public_url: str) -> str:
        """
        По публичной ссылке (disk.yandex.ru/d/...) на СВОЮ ЖЕ папку
        возвращает внутренний путь вида /Авито/Фото, с которым уже можно
        работать через обычные методы /resources.
        """
        resp = requests.get(
            f"{API_BASE}/public/resources",
            params={"public_key": public_url, "limit": 1},
            headers=self.headers,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        path = data.get("path")  # например "disk:/Авито/Фото"
        if not path:
            raise RuntimeError(
                "Не удалось получить внутренний путь. Убедись, что папка "
                "принадлежит именно этому аккаунту Яндекс.Диска."
            )
        return path.replace("disk:", "", 1)

    def ensure_folder(self, path: str):
        """Создаёт папку (и все родительские), если её ещё нет."""
        parts = [p for p in path.strip("/").split("/") if p]
        current = ""
        for part in parts:
            current += "/" + part
            resp = requests.put(
                f"{API_BASE}/resources",
                params={"path": current},
                headers=self.headers,
                timeout=15,
            )
            if resp.status_code not in (201, 409):  # 201 создано, 409 уже есть
                resp.raise_for_status()

    def file_exists(self, path: str) -> bool:
        resp = requests.get(
            f"{API_BASE}/resources",
            params={"path": path, "fields": "name"},
            headers=self.headers,
            timeout=15,
        )
        return resp.status_code == 200

    def upload_file(self, local_path: str, remote_path: str, overwrite: bool = False) -> str:
        """Загружает локальный файл на Диск. Возвращает remote_path."""
        resp = requests.get(
            f"{API_BASE}/resources/upload",
            params={"path": remote_path, "overwrite": str(overwrite).lower()},
            headers=self.headers,
            timeout=15,
        )
        resp.raise_for_status()
        upload_url = resp.json()["href"]

        with open(local_path, "rb") as f:
            put_resp = requests.put(upload_url, files={"file": f}, timeout=120)
        put_resp.raise_for_status()

        # Яндекс иногда обрабатывает файл асинхронно — небольшая пауза для надёжности
        time.sleep(0.3)
        return remote_path

    def get_public_link(self, remote_path: str) -> str:
        """Публикует файл (если ещё не опубликован) и возвращает публичную ссылку."""
        requests.put(
            f"{API_BASE}/resources/publish",
            params={"path": remote_path},
            headers=self.headers,
            timeout=15,
        )
        resp = requests.get(
            f"{API_BASE}/resources",
            params={"path": remote_path, "fields": "public_url"},
            headers=self.headers,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("public_url", "")
