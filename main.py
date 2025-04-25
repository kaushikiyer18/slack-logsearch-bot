from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from elasticsearch import Elasticsearch
from datetime import datetime, timedelta
import urllib.parse

app = FastAPI()

# Elasticsearch credentials (replace if needed)
ES_URL = "http://clkibana.netcore.co.in:5601"
ES_USERNAME = "devops"
ES_PASSWORD = "Sm@rtL0gVu82"

def parse_slack_text(text: str):
    parts = text.split()
    data = {
        "mode": None,
        "channel": None,
        "clientid": None,
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

def validate_inputs(data: dict):
    errors = []
    if not data["mode"]:
        errors.append("Missing `mode`")
    if not data["channel"]:
        errors.append("Missing `channel`")
    if not data["clientid"]:
        errors.append("Missing `clientid`")
    return errors

def get_index(mode: str, channel: str):
    index_map = {
        ("live", "apn"): "clkube-prod-us-pnserver",
        ("sandbox", "apn"): "clkube-preprod-pnserver",
        ("live", "wpn"): "clkube-prod-us-pnserver",
        ("sandbox", "wpn"): "clkube-preprod-pnserver",
        ("live", "bpn"): "clkube-prod-us-pnserver",
        ("sandbox", "bpn"): "clkube-preprod-pnserver"
    }
    return index_map.get((mode.lower(), channel.lower()))

def parse_time_range(duration: str):
    unit = duration[-1]
    value = int(duration[:-1])
    now = datetime.utcnow()
    if unit == 'd':
        return now - timedelta(days=value)
    elif unit == 'h':
        return now - timedelta(hours=value)
    return now - timedelta(days=7)

@app.post("/logsearch")
async def handle_logsearch(request: Request):
    form = await request.body()
    decoded = urllib.parse.parse_qs(form.decode())
    text = decoded.get("text", [""])[0]
    parsed = parse_slack_text(text)

    errors = validate_inputs(parsed)
    if errors:
        return JSONResponse(
            content={"response_type": "ephemeral", "text": "⚠️ " + "\n".join(errors)},
            status_code=status.HTTP_200_OK
        )

    index = get_index(parsed["mode"], parsed["channel"])
    if not index:
        return JSONResponse(
            content={"response_type": "ephemeral", "text": f"❌ Invalid mode/channel combination."},
            status_code=status.HTTP_200_OK
        )

    start_time = parse_time_range(parsed["last"])
    start_ts = int(start_time.timestamp() * 1000)

    es = Elasticsearch(ES_URL, basic_auth=(ES_USERNAME, ES_PASSWORD), verify_certs=False)

    query = {
        "query": {
            "bool": {
                "must": [
                    {"match": {"clientId": parsed["clientid"]}},
                    {"range": {"ts": {"gte": start_ts}}}
                ]
            }
        },
        "size": 5
    }

    try:
        result = es.search(index=index, body=query)
        hits = result.get("hits", {}).get("hits", [])
    except Exception as e:
        return JSONResponse(
            content={"response_type": "ephemeral", "text": f"❌ Error querying logs: {str(e)}"},
            status_code=200
        )

    if not hits:
        return JSONResponse(
            content={"response_type": "in_channel", "text": "🔍 No logs found for given Client ID."},
            status_code=200
        )

    lines = [f"🔍 *Top {len(hits)} logs for Client ID `{parsed['clientid']}`:*"]
    for h in hits:
        src = h["_source"]
        ts = src.get("ts", "N/A")
        readable_ts = datetime.utcfromtimestamp(int(ts) / 1000).strftime("%Y-%m-%d %H:%M:%S") if ts != "N/A" else "N/A"
        lines.append(f"• `{readable_ts}` | Event: `{src.get('eventName', '-')}`")

    return JSONResponse(content={"response_type": "in_channel", "text": "\n".join(lines)}, status_code=200)
