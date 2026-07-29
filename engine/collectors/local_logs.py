"""Local log material collector."""

from __future__ import annotations

import shutil
from pathlib import Path


def import_local_materials(src: Path, dest_dir: Path) -> list[str]:
    """Copy one local file or the direct children of a log directory into Case raw/."""
    imported: list[str] = []
    if not src.exists():
        raise FileNotFoundError(f"log path does not exist: {src}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    if src.is_file():
        target = dest_dir / src.name
        shutil.copy2(src, target)
        return [str(target)]

    for child in sorted(src.iterdir()):
        target = dest_dir / child.name
        if child.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(child, target)
        else:
            shutil.copy2(child, target)
        imported.append(str(target))
    return imported
