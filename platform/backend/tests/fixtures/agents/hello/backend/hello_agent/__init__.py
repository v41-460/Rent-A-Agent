from pathlib import Path

from rent_agent_interface import RunRequest, RunResponse, make_agent_router

router = make_agent_router(Path(__file__).resolve().parents[2] / "manifest.json")


@router.post("/run", response_model=RunResponse)
def run(req: RunRequest) -> RunResponse:
    name = req.input.get("name") or req.user.display_name
    return RunResponse(
        status="ok",
        message=f"Hello, {name}",
        blocks=[
            {"type": "heading", "text": f"Hello, {name}"},
            {"type": "text", "text": f"user={req.user.id} rental={req.rental_id}"},
        ],
    )
