import os
import shutil
from pathlib import Path


HOME = Path.home()


def find_files(name: str) -> str:
    """Ищет файлы в домашней папке пользователя по части имени."""

    results = []
    search_name = name.lower()

    skip_dirs = {
        "Library",
        ".Trash",
        ".venv",
        "node_modules"
    }

    for root, dirs, files in os.walk(HOME):
        dirs[:] = [
            d for d in dirs
            if d not in skip_dirs and not d.startswith(".")
        ]

        for filename in files:
            if search_name in filename.lower():
                results.append(str(Path(root) / filename))

                if len(results) >= 20:
                    break

        if len(results) >= 20:
            break

    if not results:
        return "Файлы с таким названием не найдены."

    return "Найденные файлы:\n" + "\n".join(results)


def delete_file(path: str) -> str:
    """Перемещает файл в Корзину macOS."""

    file_path = Path(path).expanduser().resolve()

    if not file_path.exists():
        return "Файл не найден: " + str(file_path)

    if not file_path.is_file():
        return "Это не файл: " + str(file_path)

    trash = HOME / ".Trash"
    destination = trash / file_path.name

    counter = 1

    while destination.exists():
        destination = trash / (
            file_path.stem
            + " "
            + str(counter)
            + file_path.suffix
        )
        counter += 1

    shutil.move(str(file_path), str(destination))

    return "Файл перемещён в Корзину: " + file_path.name
