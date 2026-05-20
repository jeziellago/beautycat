from __future__ import annotations

import asyncio
import io
import json
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from beautycat import __version__
from beautycat.adb import Adb, AdbError
from beautycat.filters import FilterSpec, apply_filter
from beautycat.parser import LogRecord
from beautycat.presets import FilterPreset, PresetStore
from beautycat.session import SessionManager


log = logging.getLogger("beautycat")


@dataclass
class AppConfig:
    adb_path: Optional[str] = None
    buffer_size: int = 10_000


def create_app(config: Optional[AppConfig] = None) -> FastAPI:
    cfg = config or AppConfig()
    adb = Adb(adb_path=cfg.adb_path)
    sessions = SessionManager(adb, buffer_size=cfg.buffer_size)
    presets = PresetStore()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            yield
        finally:
            await sessions.stop_all()

    app = FastAPI(title="BeautyCat", version=__version__, lifespan=lifespan)

    web_dir = Path(__file__).parent / "web"

    @app.get("/api/health")
    async def health() -> dict:
        return {"status": "ok", "version": __version__}

    @app.get("/api/devices")
    async def list_devices() -> dict:
        try:
            devices = await adb.list_devices()
        except AdbError as e:
            raise HTTPException(status_code=500, detail=str(e))
        return {"devices": [d.to_dict() for d in devices]}

    @app.post("/api/devices/{serial}/clear")
    async def clear_device(serial: str) -> dict:
        try:
            session = await sessions.get_or_create(serial)
            await session.clear()
        except AdbError as e:
            raise HTTPException(status_code=500, detail=str(e))
        return {"ok": True}

    @app.get("/api/devices/{serial}/export")
    async def export_logs(
        serial: str,
        fmt: str = Query("txt", pattern="^(txt|json)$"),
        level: str = Query(""),
        tag: str = Query(""),
        package: str = Query(""),
        pid: Optional[int] = Query(None),
        search: str = Query(""),
        regex: bool = Query(False),
    ):
        try:
            session = await sessions.get_or_create(serial)
        except AdbError as e:
            raise HTTPException(status_code=500, detail=str(e))

        spec = FilterSpec(
            level=level, tag=tag, package=package, pid=pid, search=search, regex=regex
        )
        records = apply_filter(session.snapshot(), spec)
        filename = f"beautycat-{serial}.{fmt}"

        if fmt == "json":
            body = json.dumps([r.to_dict() for r in records], indent=2)
            media = "application/json"
        else:
            buf = io.StringIO()
            for r in records:
                buf.write(r.to_logcat_line())
                buf.write("\n")
            body = buf.getvalue()
            media = "text/plain; charset=utf-8"

        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return StreamingResponse(iter([body]), media_type=media, headers=headers)

    @app.get("/api/presets")
    async def get_presets() -> dict:
        return {"presets": [p.to_dict() for p in presets.load()]}

    @app.post("/api/presets")
    async def save_preset(payload: dict[str, Any]) -> dict:
        if not isinstance(payload, dict) or not payload.get("name"):
            raise HTTPException(status_code=400, detail="preset 'name' is required")
        preset = FilterPreset.from_dict(payload)
        updated = presets.upsert(preset)
        return {"presets": [p.to_dict() for p in updated]}

    @app.delete("/api/presets/{name}")
    async def delete_preset(name: str) -> dict:
        updated = presets.delete(name)
        return {"presets": [p.to_dict() for p in updated]}

    @app.websocket("/ws/{serial}")
    async def ws_logs(ws: WebSocket, serial: str) -> None:
        await ws.accept()

        session = None
        listener = None
        queue: asyncio.Queue[list[LogRecord]] = asyncio.Queue(maxsize=64)

        try:
            try:
                session = await sessions.get_or_create(serial)
            except AdbError as e:
                await ws.send_json({"type": "error", "message": str(e)})
                return

            async def _listener(records: list[LogRecord]) -> None:
                try:
                    queue.put_nowait(records)
                except asyncio.QueueFull:
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                    try:
                        queue.put_nowait(records)
                    except asyncio.QueueFull:
                        pass

            listener = _listener
            session.add_listener(listener)

            await ws.send_json(
                {
                    "type": "snapshot",
                    "records": [r.to_dict() for r in session.snapshot()],
                }
            )

            async def reader() -> None:
                # Drain client messages; returns on disconnect.
                while True:
                    await ws.receive_text()

            async def sender() -> None:
                while True:
                    batch = await queue.get()
                    await ws.send_json(
                        {
                            "type": "append",
                            "records": [r.to_dict() for r in batch],
                        }
                    )

            tasks = {asyncio.create_task(reader()), asyncio.create_task(sender())}
            try:
                _, pending = await asyncio.wait(
                    tasks, return_when=asyncio.FIRST_COMPLETED
                )
            finally:
                for t in tasks:
                    t.cancel()
                # Await cancellations so they don't leak warnings.
                await asyncio.gather(*tasks, return_exceptions=True)
        except (WebSocketDisconnect, RuntimeError, ConnectionError):
            # Client closed the socket (or transport went away). Just finish.
            pass
        finally:
            if session is not None and listener is not None:
                session.remove_listener(listener)

    if web_dir.is_dir():
        @app.get("/")
        async def index() -> FileResponse:
            return FileResponse(web_dir / "index.html")

        app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")

    return app
