from fastapi import FastAPI, Form
from fastapi.responses import PlainTextResponse
from elasticsearch import Elasticsearch

app = FastAPI()

# Elasticsearch setup
es = Elasticsearch("http://clkibana.netcore.co.in:5601", basic_auth=("devops", "Sm@rtL0gVu82"))

@app.post("/logsearch")
async def logsearch(clientid: str = Form(...)):
    try:
        index = "clkube-prod-us-pnserver"
        query = {
            "query": {
                "match": {
                    "clientId": clientid
                }
            }
        }
        result = es.search(index=index, body=query)
        hits = result["hits"]["hits"]

        if not hits:
            return PlainTextResponse("No logs found for clientId: " + clientid)

        logs = []
        for hit in hits[:5]:
            log = hit["_source"]
            log_time = log.get("ts", "N/A")
            logs.append(f"- Timestamp: {log_time}, Message: {log}")

        return PlainTextResponse("\n".join(logs))

    except Exception as e:
        return PlainTextResponse(f"Error querying logs: {str(e)}")
