import os
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv

# Import degli agenti (Core-Connector-Policies)
from agent_predictive import PredictiveAgent
from agent_forger import ForgerAgent

# Carichiamo le variabili dal file .env (o dall'ambiente Docker)
load_dotenv()

# Inizializzazione FastAPI
app = FastAPI()

class CommandEvent(BaseModel):
    session_id: str
    timestamp: str
    ip: str
    user: str
    cwd: str
    cmd: str

class Orchestrator:
    def __init__(self):
        # Inizializziamo il Logger passandogli il path del DB Vettoriale
        self.predictive = PredictiveAgent()
        # Inizializziamo il Falsario
        self.forger = ForgerAgent()    

    async def dispatch(self, event: CommandEvent):
        """Gestisce il flusso sequenziale: Predizione -> Preparazione Trappola"""
        print(f"\n[ORCHESTRATOR] 📥 Nuovo comando intercettato: '{event.cmd}'")

        # --- FASE 1: LOGGER (PREDIZIONE + RAG) ---        
        print(f"[ORCHESTRATOR] 🔍 Fase 1: Analisi e Predizione in corso...")
        predicted_cmd = await self.predictive.decide(event)
        print(f"[ORCHESTRATOR] 🔍 Fase 1 terminata")
 
        # --- FASE 2: FALSARIO (PROATTIVITÀ) ---
        if predicted_cmd:
            print(f"[ORCHESTRATOR] 🔮 Fase 2: Predizione ricevuta! '{predicted_cmd}'")
            await self.forger.decide(event)
        else:
            print("[ORCHESTRATOR] ➖ Nessuna predizione rilevante. Salto fase Falsario.")

# Istanza globale dell'orchestratore configurata con gli input
orch = Orchestrator()

@app.post("/new_command")
async def handle_new_command(event: CommandEvent):
    """
    Endpoint di ricezione dalla fakeshell.
    Il 'await' garantisce che il server gestisca correttamente le attese di rete (LLM/MCP)
    senza bloccare l'intero sistema per altri attaccanti.
    """
    await orch.dispatch(event)
    return {"status": "success", "message": "Evento processato sequenzialmente"}