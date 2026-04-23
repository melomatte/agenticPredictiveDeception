import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv

# Import degli agenti (Core-Connector-Policies)
from agent_predictive import PredictiveAgent
from agent_forger import ForgerAgent

# Carichiamo le variabili dal file .env (o dall'ambiente Docker)
load_dotenv()

class CommandEvent(BaseModel):
    session_id: str
    timestamp: str
    ip: str
    user: str
    cwd: str
    cmd: str

class Orchestrator:
    def __init__(self):
        # Gli agenti vengono costruiti ma la connessione SSE non è ancora aperta
        self.predictive = PredictiveAgent()
        self.forger = ForgerAgent()

    async def __aenter__(self):
        """Apre le connessioni SSE di tutti gli agenti che le richiedono."""
        print("[ORCHESTRATOR] 🔌 Apertura connessioni agenti...")
        await self.predictive.__aenter__()
        # Se anche ForgerAgent diventerà un async context manager, aggiungilo qui:
        # await self.forger.__aenter__()
        print("[ORCHESTRATOR] ✅ Connessioni agenti aperte.")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Chiude le connessioni SSE di tutti gli agenti."""
        print("[ORCHESTRATOR] 🔌 Chiusura connessioni agenti...")
        await self.predictive.__aexit__(exc_type, exc_val, exc_tb)
        # await self.forger.__aexit__(exc_type, exc_val, exc_tb)
        print("[ORCHESTRATOR] ✅ Connessioni agenti chiuse.")

    async def dispatch(self, event: CommandEvent):
        """Gestisce il flusso sequenziale: Predizione -> Preparazione Trappola"""
        print(f"\n[ORCHESTRATOR] 📥 Nuovo comando intercettato: '{event.cmd}'")

        # --- FASE 1: PREDIZIONE + RAG ---
        print(f"[ORCHESTRATOR] 🔍 Fase 1: Analisi e Predizione in corso...")
        predicted_cmd = await self.predictive.decide(event)
        print(f"[ORCHESTRATOR] 🔍 Fase 1 terminata")

        # --- FASE 2: FALSARIO (PROATTIVITÀ) ---
        if predicted_cmd:
            print(f"[ORCHESTRATOR] 🔮 Fase 2: Predizione ricevuta! '{predicted_cmd}'")
            await self.forger.decide(event)
        else:
            print("[ORCHESTRATOR] ➖ Nessuna predizione rilevante. Salto fase Falsario.")


# --- Lifespan: gestisce startup e shutdown dell'intera applicazione ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Tutto ciò che sta prima del 'yield' viene eseguito all'avvio del server.
    Tutto ciò che sta dopo viene eseguito allo shutdown.
    L'orchestratore (e le connessioni SSE degli agenti) vivono esattamente
    quanto il server FastAPI.
    """
    async with Orchestrator() as orch:
        print("[ORCHESTRATOR] 🚀 Server pronto a ricevere eventi.")
        app.state.orch = orch   # rendiamo l'orchestratore accessibile agli endpoint
        yield                   # il server è attivo e serve le richieste
    # Uscendo dal 'async with', __aexit__ chiude automaticamente tutte le connessioni


# Inizializzazione FastAPI con lifespan
app = FastAPI(lifespan=lifespan)

@app.post("/new_command")
async def handle_new_command(event: CommandEvent):
    """
    Endpoint di ricezione dalla fakeshell.
    Recupera l'orchestratore dallo stato dell'app, già inizializzato con le
    connessioni SSE aperte.
    """
    await app.state.orch.dispatch(event)
    return {"status": "success", "message": "Evento processato sequenzialmente"}