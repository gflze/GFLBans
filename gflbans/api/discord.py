import json

from fastapi import APIRouter, Header, HTTPException
from starlette.requests import Request

from gflbans.internal.config import MONGO_DB
from gflbans.internal.discord_calladmin import handle_interaction, verify_interaction

discord_router = APIRouter()


# Set as the Interactions Endpoint URL of the Discord application, which delivers call admin claim button presses here
@discord_router.post('/interactions', include_in_schema=False)
async def interactions(
    request: Request,
    x_signature_ed25519: str = Header(None),
    x_signature_timestamp: str = Header(None),
):
    body = await request.body()

    # Discord requires invalid signatures to be rejected, and periodically sends bad ones to check that they are
    if not verify_interaction(body, x_signature_ed25519, x_signature_timestamp):
        raise HTTPException(detail='Invalid request signature', status_code=401)

    return await handle_interaction(request.app.state.db[MONGO_DB], json.loads(body))
