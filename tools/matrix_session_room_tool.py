"""Scoped Matrix session-room management for Morrigan."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from tools.registry import registry


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name, default) or "").strip()


def _registry_path() -> Path:
    from hermes_constants import get_hermes_home

    root = get_hermes_home() / "matrix-session-rooms"
    root.mkdir(parents=True, exist_ok=True)
    return root / "registry.json"


def _load_registry() -> Dict[str, Any]:
    path = _registry_path()
    if not path.exists():
        return {"rooms": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"rooms": []}


def _save_registry(data: Dict[str, Any]) -> None:
    _registry_path().write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _allowed_users() -> List[str]:
    raw = _env("MATRIX_SESSION_ALLOWED_USERS")
    return [u.strip() for u in raw.split(",") if u.strip()]


def _in_scope(room: Dict[str, Any], space_id: str) -> bool:
    return room.get("space_id") == space_id


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tool_error(msg: str) -> str:
    return json.dumps({"success": False, "error": msg})


def _build_adapter():
    from gateway.config import Platform, PlatformConfig
    from gateway.platforms.matrix import MatrixAdapter

    cfg = PlatformConfig(enabled=True, token=_env("MATRIX_ACCESS_TOKEN"), extra={
        "homeserver": _env("MATRIX_HOMESERVER"),
        "user_id": _env("MATRIX_USER_ID"),
        "password": _env("MATRIX_PASSWORD"),
        "encryption": _env("MATRIX_ENCRYPTION", "true").lower() in ("true", "1", "yes"),
        "device_id": _env("MATRIX_DEVICE_ID"),
    })
    return MatrixAdapter(cfg), Platform


async def _run_action(action: str, name: str = "", room_id: str = "", destination_room_id: str = "") -> Dict[str, Any]:
    del destination_room_id
    space_id = _env("MATRIX_SESSION_SPACE_ID")
    if not space_id:
        return {"success": False, "error": "MATRIX_SESSION_SPACE_ID not configured"}

    db = _load_registry()
    rooms = db.get("rooms", [])

    if action == "list":
        scoped = [r for r in rooms if _in_scope(r, space_id)]
        return {"success": True, "space_id": space_id, "rooms": scoped}

    if action == "archive":
        if not room_id:
            return {"success": False, "error": "room_id is required for archive"}
        row = next((r for r in rooms if r.get("room_id") == room_id and _in_scope(r, space_id)), None)
        if not row:
            return {"success": False, "error": "room is not registered under configured session space"}

        adapter, _ = _build_adapter()
        try:
            if not await adapter.connect():
                return {"success": False, "error": "Matrix connect failed"}
            removed = await adapter.remove_room_from_space(space_id, room_id)
            if not removed:
                return {"success": False, "error": "failed removing room from space"}
        finally:
            await adapter.disconnect()

        row["status"] = "archived"
        row["archived_at"] = _now()
        _save_registry(db)
        return {"success": True, "archived": room_id, "space_id": space_id}

    if action == "create":
        if not name:
            return {"success": False, "error": "name is required for create"}
        adapter, _ = _build_adapter()
        try:
            if not await adapter.connect():
                return {"success": False, "error": "Matrix connect failed"}

            allowed = _allowed_users()
            room_new = await adapter.create_room(
                name=name,
                topic=f"Morrigan session room: {name}",
                invite=allowed,
                is_direct=False,
                preset="private_chat",
            )
            if not room_new:
                return {"success": False, "error": "failed to create room"}

            if not await adapter.add_room_to_space(space_id, room_new):
                return {"success": False, "error": "failed to add room to session space"}
            await adapter.set_room_parent_space(room_new, space_id)

            rec = {
                "room_id": room_new,
                "name": name,
                "status": "active",
                "space_id": space_id,
                "created_at": _now(),
                "archived_at": None,
            }
            rooms.append(rec)
            _save_registry(db)

            return {
                "success": True,
                "room": rec,
                "link": f"https://matrix.to/#/{room_new}",
            }
        finally:
            await adapter.disconnect()

    if action == "link":
        if not room_id:
            return {"success": False, "error": "room_id is required for link"}
        row = next((r for r in rooms if r.get("room_id") == room_id and _in_scope(r, space_id)), None)
        if not row:
            return {"success": False, "error": "room is not registered under configured session space"}
        return {"success": True, "link": f"https://matrix.to/#/{room_id}", "room": row}

    if action == "merge":
        return {
            "success": False,
            "error": "merge is not implemented yet; use manual summary + archive workflow",
        }

    return {"success": False, "error": f"unknown action: {action}"}


def matrix_session_room_tool(args, **kw):
    del kw
    action = (args.get("action") or "").strip().lower()
    name = (args.get("name") or "").strip()
    room_id = (args.get("room_id") or "").strip()
    destination_room_id = (args.get("destination_room_id") or "").strip()
    if not action:
        return _tool_error("action is required")
    from model_tools import _run_async

    result = _run_async(_run_action(action, name=name, room_id=room_id, destination_room_id=destination_room_id))
    return json.dumps(result)


MATRIX_SESSION_ROOM_SCHEMA = {
    "name": "matrix_session_room",
    "description": "Manage Morrigan session rooms inside the configured Matrix space.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "create", "archive", "link", "merge"],
                "description": "Operation to execute.",
            },
            "name": {
                "type": "string",
                "description": "Room name for create.",
            },
            "room_id": {
                "type": "string",
                "description": "Matrix room ID for link/archive/merge source.",
            },
            "destination_room_id": {
                "type": "string",
                "description": "Destination room ID for merge.",
            },
        },
        "required": ["action"],
    },
}


def _check_matrix_session_reqs() -> bool:
    return bool(_env("MATRIX_HOMESERVER") and (_env("MATRIX_ACCESS_TOKEN") or (_env("MATRIX_USER_ID") and _env("MATRIX_PASSWORD"))))


registry.register(
    name="matrix_session_room",
    toolset="messaging",
    schema=MATRIX_SESSION_ROOM_SCHEMA,
    handler=matrix_session_room_tool,
    check_fn=_check_matrix_session_reqs,
    emoji="🏠",
)
