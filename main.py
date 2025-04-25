from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
import urllib.parse
import uvicorn

app = FastAPI()

VALID_CHANNELS = ["apn", "wpn", "bpn"]
VALID_MODES = ["sandbox", "live"]

LOG_INDEX_MAP = {
    "sandbox": "clkube-preprod-pnserver",
    "live": "clkube-prod-us-pnserver"
}

def parse_slack_text(text: str) -> dict:
    parts = text.split()
    data = {
        "mode": None,
        "channel": None,
        "clientid": None,
        "userid": None,
        "eventname": None,
        "trid": None,
        "primarykey": None,
        "last": "7d"
    }
    for part in parts:
        if "=" in part:
            key, value = part.split("=", 1)
            if key in data:
                data[key] = value
        elif part.startswith("--last="):
            data["last"] = part.replace("--last=", "")
    return data

def validate_fields(data: dict) -> list:
    errors = []
    required_fields = ["mode", "channel", "clientid", "userid", "eventname", "trid", "primarykey"]
    for field in required_fields:
        if not data.get(field):
            errors.append(f"Missing `{field}`")
    if data["mode"] and data["mode"].lower() not in VALID_MODES:
        errors.append(f"Invalid mode: `{data['mode']}`. Use `sandbox` or `live`.")
    if data["channel"] and data["channel"].lower() not in VALID_CHANNELS:
        errors.append(f"Invalid channel: `{data['channel']}`. Use `apn`, `wpn`, or `bpn`.")
    return errors

@app.post("/logsearch")
async def handle_logsearch(request: Request):
    form = await request.body()
    decoded = urllib.parse.parse_qs(form.decode())
    text = decoded.get("text", [""])[0]

    parsed = parse_slack_text(text)
    errors = validate_fields(parsed)

    if errors:
        return JSONResponse(
            content={"response_type": "ephemeral", "text": "⚠️ " + "\n".join(errors)},
            status_code=status.HTTP_200_OK
        )

    mode = parsed["mode"].lower()
    index = LOG_INDEX_MAP.get(mode, "unknown")

    message = (
        f"🔍 *Log search received for `{parsed['channel'].upper()}` in `{mode.upper()}` mode:*\n\n"
        f"- Client ID: `{parsed['clientid']}`\n"
        f"- User ID: `{parsed['userid']}`\n"
        f"- Event Name: `{parsed['eventname']}`\n"
        f"- TRID: `{parsed['trid']}`\n"
        f"- Primary Key (part of TRID): `{parsed['primarykey']}`\n"
        f"- Time Range: *Last {parsed['last']}*\n\n"
        f"📁 Searching in index: `{index}`"
    )

    return JSONResponse(content={"response_type": "in_channel", "text": message}, status_code=status.HTTP_200_OK)
