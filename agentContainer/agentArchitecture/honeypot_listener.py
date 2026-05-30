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
import os
import asyncio
from typing import List
from fastapi import FastAPI
from pydantic import BaseModel
from agent_predictive import PredictiveAgent
from agent_forger import ForgerAgent

# Carichiamo le variabili dal file .env (o dall'ambiente Docker)
PROVIDER = os.getenv("PROVIDER")
MODEL_NAME = os.getenv("MODEL_NAME")
BACKEND_MCP_URL = os.getenv("BACKEND_MCP_URL")
FORGERY_MCP_URL = os.getenv("FORGERY_MCP_URL")
NUM_PREDICTION = os.getenv("NUM_PREDICTION")

# Struttura evento ricevuta da fakeshell
class CommandEvent(BaseModel):
    session_id: str
    timestamp: str
    ip: str
    user: str
    cwd: str
    cmd: str

class HoneypotListener:
    def __init__(self):
        self.predictive = PredictiveAgent(mcp_url=BACKEND_MCP_URL, model_name=MODEL_NAME, provider=PROVIDER, k=NUM_PREDICTION)
        self.forgers: List[ForgerAgent] = [ForgerAgent(mcp_url_backend=BACKEND_MCP_URL, mcp_url_forgery=FORGERY_MCP_URL,model_name=MODEL_NAME, provider=PROVIDER, id= i) for i in range(int(NUM_PREDICTION))]

    async def __aenter__(self):
        print("[HONEYPOT LISTENER] Apertura connessioni agenti...")
        await self.predictive.__aenter__()
        for forger in self.forgers:
            await forger.__aenter__()
        print("[HONEYPOT LISTENER] Connessioni agenti aperte.")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        print("[HONEYPOT LISTENER] Chiusura connessioni agenti...")
        await self.predictive.__aexit__(exc_type, exc_val, exc_tb)
        for forger in self.forgers:
            await forger.__aexit__(exc_type, exc_val, exc_tb)
        print("[HONEYPOT LISTENER] Connessioni agenti chiuse.")

    async def dispatch(self, event: CommandEvent):
        print(f"\n[HONEYPOT LISTENER] Nuovo comando intercettato: '{event.cmd}'")

        # --- FASE 1: PREDIZIONE + RAG ---
        print(f"[HONEYPOT LISTENER] Fase 1: Analisi e Predizione in corso...")
        predicted_cmd = await self.predictive.decide(event)
        print(f"[HONEYPOT LISTENER] Comandi predetti: {predicted_cmd}")
        print(f"[HONEYPOT LISTENER] Fase 1 terminata")

        if not predicted_cmd:
            print("[HONEYPOT LISTENER] Nessuna predizione ricevuta. Salto la fase di creazione artefatti")
            return
            
        # --- FASE 2: FORGER ---
        num_active_forgers = min(len(predicted_cmd), len(self.forgers))
        print(f"\n[HONEYPOT LISTENER] Fase 2: avvio lavoro di {num_active_forgers} agent forger in parallelo...")
        tasks = [
            forger.decide(cmd, event)
            for cmd, forger in zip(predicted_cmd, self.forgers)
        ]
        asyncio_tasks = [asyncio.create_task(t) for t in tasks]

        # Attendiamo massimo 180 secondi (3 minuti)
        done, pending = await asyncio.wait(asyncio_tasks, timeout=180.0)

        result = []

        # 1. Recuperiamo i risultati di chi ha finito in tempo
        for task in done:
            try:
                # task.result() restituisce l'output, o lancia l'eccezione se l'agente è andato in crash
                res = task.result()
                result.append(res)
            except Exception as e:
                print(f"[HONEYPOT LISTENER] ⚠️ Errore interno in uno degli agenti: {e}")
                result.append([]) 

        # 2. Gestiamo i "ritardatari" (Quelli bloccati dopo 3 minuti)
        if pending:
            print(f"\n[HONEYPOT LISTENER] ⚠️ TIMEOUT: {len(pending)} agenti non hanno finito entro 3 minuti.")
            for task in pending:
                task.cancel()
        print(f"[HONEYPOT LISTENER] Artefatti generati: {result}")
        print("[HONEYPOT LISTENER] Fase 2: fase 2 terminata per tutte le predizioni.")

# --- Lifespan: gestisce startup e shutdown dell'intera applicazione ---

@asynccontextmanager
async def lifespan(app: FastAPI):

    # Uscendo dal 'async with', __aexit__ chiude automaticamente tutte le connessioni
    async with HoneypotListener() as orch:
        print("[HONEYPOT LISTENER] 🚀 Server pronto a ricevere eventi.")
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