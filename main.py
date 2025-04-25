from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
import urllib.parse
from elasticsearch import Elasticsearch
from datetime import datetime, timedelta
import os

app = FastAPI()

# Elasticsearch config (💡 Use ENV VARS in prod)
ES_USERNAME = "devops"
ES_PASSWORD = "Sm@rtL0gVu82"
ES_URL = "http://clkibana.netcore.co.in:5601"

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

def parse_time_range(duration: str):
    unit = duration[-1]
    value = int(duration[:-1])
    now = datetime.utcnow()
    if unit == 'd':
        return now - timedelta(days=value)
    elif unit == 'h':
        return now - timedelta(hours=value)
    elif unit == 'm':
        return now - timedelta(minutes=value)
    return now - timedelta(days=7)

def build_query(data: dict, start_ts_ms: int):
    return {
        "query": {
            "bool": {
                "must": [
                    {"match": {"clientId": data["clientid"]}},
                    {"match": {"userId": data["userid"]}},
                    {"match": {"eventName": data["eventname"]}},
                    {
                        "bool": {
                            "should": [
                                {"wildcard": {"trId": f"*{data['primarykey']}*"}},
                                {"wildcard": {"payload.trid": f"*{data['primarykey']}*"}}
                            ]
                        }
                    },
                    {"range": {"ts": {"gte": start_ts_ms}}}
                ]
            }
        },
        "size": 5
    }

@app.post("/logsearch")
async def handle_logsearch(request: Request):
    form = await request.body()
    decoded = urllib.parse.parse_qs(form.decode())
    text = decoded.get("text", [""])[0]

    parsed = parse_slack_text(text)
    errors = validate_fields(parsed)
    if errors:
        return JSONResponse(content={"response_type": "ephemeral", "text": "⚠️ " + "\n".join(errors)}, status_code=status.HTTP_200_OK)

    mode = parsed["mode"].lower()
    index = LOG_INDEX_MAP.get(mode, "unknown")
    start_time = parse_time_range(parsed["last"])
    start_ts_ms = int(start_time.timestamp() * 1000)

    # Connect to Elasticsearch
    es = Elasticsearch(ES_URL, basic_auth=(ES_USERNAME, ES_PASSWORD), verify_certs=False)

    # Build query
    es_query = build_query(parsed, start_ts_ms)
    try:
        result = es.search(index=index, body=es_query)
        hits = result.get("hits", {}).get("hits", [])
    except Exception as e:
        return JSONResponse(content={"response_type": "ephemeral", "text": f"❌ Error querying logs: {str(e)}"}, status_code=200)

    # Format results
    if not hits:
        return JSONResponse(content={"response_type": "in_channel", "text": "🔍 No matching logs found."}, status_code=200)

    lines = [f"🔍 *Top {len(hits)} logs from `{index}`:*"]
    for h in hits:
        src = h["_source"]
        ts = src.get("ts", "N/A")
        ts_readable = datetime.utcfromtimestamp(int(ts) / 1000).strftime("%Y-%m-%d %H:%M:%S") if ts != "N/A" else "N/A"
        lines.append(f"• `{ts_readable}` | Event: `{src.get('eventName', '-')}` | ClientID: `{src.get('clientId', '-')}` | UserID: `{src.get('userId', '-')}`")

    return JSONResponse(content={"response_type": "in_channel", "text": "\n".join(lines)}, status_code=200)

# Local test if needed
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", port=10000, host="0.0.0.0", reload=True)
