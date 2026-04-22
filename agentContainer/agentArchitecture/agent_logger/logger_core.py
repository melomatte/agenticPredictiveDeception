import json
import os
import httpx
from agent_connector import AgentConnector
from logger_policies import LOGGER_SYSTEM, LOGGER_RULES, ORCHESTRATOR_CONTEXT

class LoggerAgent:
    def __init__(self, model_name="gpt-4o-mini", provider="cloud"):
        self.id = "Logger_01"
        self.brain = AgentConnector(provider=provider, model_name=model_name)
        self.mcp_url = os.getenv("MCP_SERVER_URL", "http://mcp-server:8000")
        
        # Assemblaggio prompt statico
        self.static_prompt = f"{LOGGER_SYSTEM}\n\n{LOGGER_RULES}"

    def _format_metrics_to_text(self, metrics):
        """Converte l'oggetto evento in testo compatto per l'LLM."""
        return (
            f"--- DATI RAW RICEVUTI ---\n"
            f"Timestamp: {metrics.timestamp}\n"
            f"IP Attaccante: {metrics.ip}\n"
            f"Utente: {metrics.user}\n"
            f"Directory: {metrics.cwd}\n"
            f"Comando: {metrics.cmd}\n"
        )

    async def decide(self, current_metrics, global_directive=None):
        metrics_text = self._format_metrics_to_text(current_metrics)

        if global_directive is None:
            global_directive = {"action": "log_standard", "reasoning": "Nessuna direttiva specifica"}

        orchestrator_text = ORCHESTRATOR_CONTEXT.format(
            action=global_directive.get("action"),
            reasoning=global_directive.get("reasoning"),
        )

        final_prompt = f"{self.static_prompt}\n\n{orchestrator_text}\n\n{metrics_text}\n\nGenera il JSON:"

        # 1. Pensiero (Chiamata LLM)
        raw_response = await self.brain.think(final_prompt)
        text = raw_response.content.strip().replace("```json", "").replace("```", "")

        try:
            parsed_log = json.loads(text)
            print(f"📝 [{self.id}] Log elaborato con Threat Level: {parsed_log.get('data', {}).get('threat_level')}")
            
            # 2. Azione fisica (Chiamata MCP per scrivere il file)
            async with httpx.AsyncClient() as client:
                await client.post(f"{self.mcp_url}/log", json=parsed_log, timeout=1.0)
            
            return parsed_log
        except Exception as e:
            print(f"⚠️ [{self.id}] JSON non valido o errore MCP: {e}\nTesto raw: {text}")
            return None