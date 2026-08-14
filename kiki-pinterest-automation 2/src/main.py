"""
Оркестратор: Pinterest -> дедупликация -> Яндекс.Диск.

Запуск:
    python src/main.py

Настройки:
    - config/boards.csv        список досок и целевых подпапок (пополняется вручную)
    - registry.csv              реестр уже обработанных пинов (создаётся и растёт сам)
    - переменная окружения YADISK_TOKEN
    - переменная окружения YADISK_ROOT_PUBLIC_URL (ссылка на корневую папку Авито-облака)
"""
import csv
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from registry import Registry, file_md5  # noqa: E402
from yadisk import YaDiskClient  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BOARDS_CSV = ROOT / "config" / "boards.csv"
REGISTRY_CSV = ROOT / "registry.csv"
IMAGES_PER_BOARD = int(os.environ.get("IMAGES_PER_RUN", "200"))


def load_boards():
    boards = []
    with open(BOARDS_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = (row.get("board_url") or "").strip()
            subfolder = (row.get("yadisk_subfolder") or "").strip()
            if url:
                boards.append((url, subfolder))
    return boards


def scrape_board(board_url: str, tmpdir: str):
    """Запускает pin-dl, скачивает фото во временную папку, возвращает список dict-описаний."""
    cmd = [
        "pin-dl", "scrape", board_url,
        "-n", str(IMAGES_PER_BOARD),
        "-o", tmpdir,
        "--json",
        "--caption", "none",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if result.returncode != 0:
        print(f"  [!] Ошибка скрапинга {board_url}: {result.stderr[-2000:]}", file=sys.stderr)
        return []
    import json
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"  [!] Не удалось разобрать JSON для {board_url}", file=sys.stderr)
        return []
    return payload.get("media", payload if isinstance(payload, list) else [])


def main():
    token = os.environ.get("YADISK_TOKEN")
    root_public_url = os.environ.get("YADISK_ROOT_PUBLIC_URL")
    if not token or not root_public_url:
        print("Заданы не все переменные окружения: YADISK_TOKEN, YADISK_ROOT_PUBLIC_URL", file=sys.stderr)
        sys.exit(1)

    yadisk = YaDiskClient(token)
    root_path = yadisk.resolve_public_path(root_public_url)
    print(f"Корневая папка на Диске: {root_path}")

    registry = Registry(str(REGISTRY_CSV))
    boards = load_boards()
    if not boards:
        print("config/boards.csv пуст — добавь хотя бы одну доску.")
        return

    total_new = 0
    for board_url, subfolder in boards:
        print(f"\n=== Доска: {board_url} -> {subfolder or '(корень)'} ===")
        remote_folder = f"{root_path}/{subfolder}".rstrip("/") if subfolder else root_path
        yadisk.ensure_folder(remote_folder)

        with tempfile.TemporaryDirectory() as tmpdir:
            items = scrape_board(board_url, tmpdir)
            print(f"  Найдено медиа: {len(items)}")

            for item in items:
                pin_id = str(item.get("id", ""))
                pin_url = item.get("origin", "")
                local_path = item.get("local_path")

                if not local_path or not os.path.exists(local_path):
                    continue  # видео/не скачалось

                file_hash = file_md5(local_path)

                if registry.is_known(pin_id, file_hash):
                    os.remove(local_path)
                    continue  # уже обрабатывали раньше — пропускаем, без дублей

                ext = Path(local_path).suffix or ".jpg"
                remote_filename = f"{pin_id}{ext}"
                remote_path = f"{remote_folder}/{remote_filename}"

                if yadisk.file_exists(remote_path):
                    # На всякий случай — если файл с таким именем уже там лежит
                    os.remove(local_path)
                    continue

                yadisk.upload_file(local_path, remote_path)
                public_link = yadisk.get_public_link(remote_path)

                registry.add({
                    "pin_id": pin_id,
                    "pin_url": pin_url,
                    "file_hash": file_hash,
                    "filename": remote_filename,
                    "board_url": board_url,
                    "yadisk_path": remote_path,
                    "yadisk_public_link": public_link,
                    "downloaded_at": datetime.now(timezone.utc).isoformat(),
                })

                os.remove(local_path)
                total_new += 1
                print(f"  + новое фото загружено: {remote_filename}")

    print(f"\nГотово. Новых фото загружено: {total_new}")


if __name__ == "__main__":
    main()
