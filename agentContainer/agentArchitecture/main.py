from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
from agentContainer.agentArchitecture.orchestrator import Orchestrator

# Carica il file .env prima di istanziare gli agenti
load_dotenv()

app = FastAPI()
orch = Orchestrator()

class CommandEvent(BaseModel):
    timestamp: str
    ip: str
    user: str
    cwd: str
    cmd: str

@app.post("/new_command")
async def handle_new_command(event: CommandEvent):
    # Passa la palla all'Orchestratore in modo asincrono
    await orch.dispatch(event)
    return {"status": "dispatched"}