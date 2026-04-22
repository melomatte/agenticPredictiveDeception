import asyncio
from agent_logger import LoggerAgent
from agent_forger import ForgerAgent

class Orchestrator:
    def __init__(self):
        # Istanziamo i due agenti
        self.logger = LoggerAgent()
        self.falsario = ForgerAgent()

    async def dispatch(self, event):
        print(f"\n⚡ [ORCHESTRATOR] Nuovo evento da {event.ip}: {event.cmd}")
        
        # Creiamo la direttiva globale (in futuro potrebbe variare dinamicamente)
        global_directive = {
            "action": "standard_monitoring",
            "reasoning": "Logga l'evento e genera esche se necessario."
        }

        # Lanciamo le funzioni `decide` in parallelo
        tasks = [
            asyncio.create_task(self.logger.decide(event, global_directive)),
            asyncio.create_task(self.falsario.decide(event, global_directive))
        ]
        
        # Aspettiamo il completamento (con timeout per sbloccare la fakeshell)
        try:
            await asyncio.wait(tasks, timeout=2.5, return_when=asyncio.ALL_COMPLETED)
        except Exception as e:
            print(f"⚠️ [ORCHESTRATOR] Errore nel loop concorrente: {e}")