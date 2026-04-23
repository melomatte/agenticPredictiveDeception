"""
Orchestrator — Punto di ingresso e coordinamento del sistema agentico legato all'honeypot.

Questo modulo espone un server FastAPI che riceve gli eventi dalla fakeshell (ogni comando digitato da un attaccante) e coordina 
il flusso di lavoro tra i vari agenti AI del sistema.

La gestione del ciclo di vita avviene con asynccontextmanager. Il problema centrale è che gli agenti AI mantengono connessioni 
di rete persistenti (SSE verso il server MCP backend) che devono essere aperte prima che il server inizi a ricevere richieste e 
chiuse in modo ordinato allo shutdown. Per garantire questo, si utilizza il meccanismo 'lifespan' di FastAPI, decorato
con asynccontextmanager. Tutto il codice prima dello 'yield' viene eseguito all'avvio dell'app, mentre tutto quello dopo 
viene eseguito allo spegnimento.

Per come è stato scritto il codice di lifespan, l'Orchestrator è esso stesso un async context manager con i due metodi:
__aenter__ -> all'entrata apre le connessioni SSE di tutti gli agenti che ne hanno bisogno (chiamando a sua volta i loro metodi __aenter__)
__aexit__ -> all'uscita le chiude in modo garantito anche in caso di eccezione (chiamando a sua volta i loro metodi __aexit__)

L'istanza dell'orchestratore (con le connessioni già aperte) viene salvata in app.state.orch, rendendola accessibile a tutti 
gli endpoint senza usare variabili globali.

FLUSSO DI DISPATCH:
    1. Fase Predizione: PredictiveAgent analizza il comando e predice i successivi.
    2. Fase Falsario:   ForgerAgent prepara risposte ingannevoli basate sulla predizione.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
from agent_predictive import PredictiveAgent
from agent_forger import ForgerAgent

# Carichiamo le variabili dal file .env (o dall'ambiente Docker)
load_dotenv()

# Struttura evento ricevuta da fakeshell
class CommandEvent(BaseModel):
    session_id: str
    timestamp: str
    ip: str
    user: str
    cwd: str
    cmd: str

class Orchestrator:
    def __init__(self):
        self.predictive = PredictiveAgent()
        self.forger = ForgerAgent()

    async def __aenter__(self):
        print("[ORCHESTRATOR] 🔌 Apertura connessioni agenti...")
        await self.predictive.__aenter__()
        # Se anche ForgerAgent diventerà un async context manager, aggiungilo qui:
        # await self.forger.__aenter__()
        print("[ORCHESTRATOR] ✅ Connessioni agenti aperte.")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        print("[ORCHESTRATOR] 🔌 Chiusura connessioni agenti...")
        await self.predictive.__aexit__(exc_type, exc_val, exc_tb)
        # await self.forger.__aexit__(exc_type, exc_val, exc_tb)
        print("[ORCHESTRATOR] ✅ Connessioni agenti chiuse.")

    async def dispatch(self, event: CommandEvent):
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
        print(f"[ORCHESTRATOR] 🔮 Fase 2 terminata")


# --- Lifespan: gestisce startup e shutdown dell'intera applicazione ---

@asynccontextmanager
async def lifespan(app: FastAPI):

    # Uscendo dal 'async with', __aexit__ chiude automaticamente tutte le connessioni
    async with Orchestrator() as orch:
        print("[ORCHESTRATOR] 🚀 Server pronto a ricevere eventi.")
        app.state.orch = orch   
        yield                   


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