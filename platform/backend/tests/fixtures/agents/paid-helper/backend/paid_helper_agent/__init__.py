from pathlib import Path

from rent_agent_interface import RunRequest, RunResponse, make_agent_router

router = make_agent_router(Path(__file__).resolve().parents[2] / "manifest.json")


@router.post("/run")
def run(req: RunRequest):
    if req.input.get("bad"):
        return {"status": "ok", "blocks": [{"type": "video"}]}  # breaks the interface on purpose
    return RunResponse(status="ok", blocks=[{"type": "text", "text": "paid ok"}])
