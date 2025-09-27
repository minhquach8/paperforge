from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from appdirs import user_config_dir

APP_NAME = "Paperforge"
APP_AUTHOR = "Paperforge"
CONFIG_DIR = Path(user_config_dir(APP_NAME, APP_AUTHOR))
CONFIG_FILE = CONFIG_DIR / "config.json"


def _default_cfg() -> Dict[str, Any]:
    return {
        "defaults": {
            "students_root": "",
            "student_name": ""
        },
        "manuscripts": {
            # key: absolute path of local working dir
            # value: { "students_root": "...", "student_name": "...", "slug": "paper-1" }
        }
    }


def load_config() -> Dict[str, Any]:
    if not CONFIG_FILE.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        cfg = _default_cfg()
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
        return cfg
    try:
        return json.loads(CONFIG_FILE.read_text())
    except Exception:
        # If corrupt, back up and reset
        backup = CONFIG_FILE.with_suffix(".bak")
        CONFIG_FILE.replace(backup)
        cfg = _default_cfg()
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
        return cfg


def save_config(cfg: Dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


def remember_defaults(students_root: str, student_name: str) -> None:
    cfg = load_config()
    cfg["defaults"]["students_root"] = students_root
    cfg["defaults"]["student_name"] = student_name
    save_config(cfg)


def remember_mapping(local_working_dir: Path, students_root: str, student_name: str, manuscript_slug: str) -> None:
    cfg = load_config()
    key = str(local_working_dir.resolve())
    cfg["manuscripts"][key] = {
        "students_root": students_root,
        "student_name": student_name,
        "slug": manuscript_slug
    }
    save_config(cfg)


def get_mapping(local_working_dir: Path) -> Optional[Dict[str, str]]:
    cfg = load_config()
    return cfg["manuscripts"].get(str(local_working_dir.resolve()))


def get_defaults() -> Dict[str, str]:
    cfg = load_config()
    return cfg.get("defaults", {"students_root": "", "student_name": ""})
