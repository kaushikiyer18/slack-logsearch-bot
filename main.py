from fastapi import FastAPI, Form
from fastapi.responses import JSONResponse

app = FastAPI()

@app.post("/logsearch")
async def logsearch(clientid: str = Form(...)):
    return JSONResponse(content={
        "response_type": "ephemeral",
        "text": f"🔍 Searching logs for `clientid={clientid}`"
    })
