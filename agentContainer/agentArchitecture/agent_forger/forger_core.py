import os
import httpx
from agent_connector import AgentConnector
from agent_forger.forger_policies import FALSARIO_SYSTEM, FALSARIO_RULES, ORCHESTRATOR_CONTEXT

class ForgerAgent:
    def __init__(self, model_name="gemini-1.5-flash", provider="cloud"):
        self.id = "FORGER AGENT"
        self.brain = AgentConnector(provider=provider, model_name=model_name)
        #self.mcp_url = os.getenv("MCP_SERVER_URL", "http://mcp-server:8000")
        
        self.static_prompt = f"{FALSARIO_SYSTEM}\n\n{FALSARIO_RULES}"

    def _format_metrics_to_text(self, metrics):
        return (
            f"--- CONTESTO ATTUALE ---\n"
            f"L'attaccante si trova in: {metrics.cwd}\n"
            f"Ha digitato il comando: {metrics.cmd}\n"
        )

    async def decide(self, current_metrics, global_directive=None):
        # Filtro veloce per risparmiare token
        if not any(k in current_metrics.cmd for k in ["cat", "less", "nano", "vi", "tail"]):
            return None

        metrics_text = self._format_metrics_to_text(current_metrics)

        if global_directive is None:
            global_directive = {"action": "deceive", "reasoning": "Genera esca realistica"}

        orchestrator_text = ORCHESTRATOR_CONTEXT.format(
            action=global_directive.get("action"),
            reasoning=global_directive.get("reasoning"),
        )

        final_prompt = f"{self.static_prompt}\n\n{orchestrator_text}\n\n{metrics_text}\n\nGenera contenuto:"

        # 1. Pensiero
        raw_response = await self.brain.think(final_prompt)
        text = raw_response.content.strip()

        if text == "IGNORE" or not text:
            print(f"➖ [{self.id}] Nessuna azione richiesta.")
            return None

        print(f"🎨 [{self.id}] Esca generata. Procedo all'iniezione.")

        # 2. Comprensione topologia (Estrae il nome file dal comando)
        target_file = current_metrics.cmd.split()[-1]
        target_path = os.path.join(current_metrics.cwd, target_file) if not target_file.startswith("/") else target_file

        # 3. Azione fisica (Chiamata MCP per iniettare nel filesystem Docker)
        payload = {"target_path": target_path, "content": text}
        try:
            async with httpx.AsyncClient() as client:
                await client.post(f"{self.mcp_url}/inject", json=payload, timeout=1.5)
            return {"action": "injected", "path": target_path}
        except Exception as e:
            print(f"❌ [{self.id}] Errore MCP: {e}")
            return None