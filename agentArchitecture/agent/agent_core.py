"""
È l'architetto logico (il "Manager") dell'agente.
Si occupa di preparare tutto il contesto necessario affinché LLM possa decidere possa decidere. Traduce la realtà fisica 
della simulazione in concetti che l'IA può capire. Gestisce: Formattazione della topologia, compressione delle metriche in testo 
e la struttura logica del processo decisionale.

3 funzioni principali:

    -  __init__(self, topology_path, model_name, provider) = preparazione del prompt statico. Carica la rete stradale JSON e 
    la converte in un formato testuale denso per massimizzare l'efficienza dei token.

    - _format_metrics_to_text(self, metrics) = Converte le metriche Live (JSON) in un formato testuale denso.
    
    - decide(self, current_metrics) = si sviluppa in 3 fasi:
        1. Assemblaggio prompt da inviare all'LLM (composto da parte statica creata in fase di init e 
        parte dinamica estrapolata dalla simulazione tramite traci al momento dell'interrogazione)
        2. Invio prompt LLM tramite modulo llm_connector.py
        3. Ricezione della risposta
"""

import json
from .agent_connector import AgentBrain
from agenticArchitecture.agent.agent_policies import (
    TOPOLOGY,
    OPTIMIZATION_RULES,
    RESPONSE_RULES,
    ORCHESTRATOR_CONTEXT,
)

class TrafficAgent:

    def __init__(self, topology_path, model_name, provider="local"):

        with open(topology_path, 'r') as f:
            self.topo = json.load(f)
        
        self.id = self.topo.get('id', 'unknown_agent')
        
        # Passiamo le preferenze al Brain
        self.brain = AgentBrain(provider=provider, model_name=model_name)
        
        # Conversione topologia da JSON a Testo (Adjacency List compatta -> per risparmio token)
        topo_text = f"AREA ID: {self.id}\n"
        
        ingressi = ", ".join(self.topo.get("in", []))
        uscite = ", ".join(self.topo.get("out", []))
        
        topo_text += f"IN (Ingressi Area): {ingressi}\n"
        topo_text += f"OUT (Uscite Area): {uscite}\n"
        topo_text += "GRAPH (Rete degli Incroci):\n"
        
        for line in self.topo.get("graph", []):
            topo_text += f"- {line}\n"

        topology_section = TOPOLOGY.format(topology_text=topo_text)

        # Assemblaggio prompt statico (sarà sempre uguale in ogni prompting) con variabili di policies.py
        self.static_prompt = f"{topology_section}\n\n{OPTIMIZATION_RULES}\n\n{RESPONSE_RULES}"

    def _format_metrics_to_text(self, metrics):
        stress = metrics.get("stress_index", 0)
        
        # English translation of qualitative stress and implicit behavioral directives
        if stress < 20: 
            status = "FLUID"
            explanation = "Traffic is flowing smoothly. No urgent intervention required, maintain current efficiency."
        elif stress < 50: 
            status = "MODERATE"
            explanation = "Traffic volume is manageable. Monitor conditions to prevent future congestion."
        elif stress < 80: 
            status = "CRITICAL"
            explanation = "Significant queues are forming. Intervention is required to unblock traffic flows."
        else: 
            status = "EMERGENCY"
            explanation = "High risk of gridlock. Absolute priority is immediate queue clearance and deadlock prevention."
        
        # Return the extremely token-efficient, English-only prompt
        return (
            f"--- ZONE STATUS: {status} (Stress Index: {stress}/100) ---\n"
            f"Operational Context: {explanation}"
        )
    
        """
        lines = [f"--- ZONE STATUS: {status} (Stress Index: {stress}/100) ---"]
        for inter in metrics.get("intersections", []):
            lanes_info = [f"{l_id}(Q:{d['queue']}, M:{d['moving']})" 
                         for l_id, d in inter.get("lanes_status", {}).items()]
            
            lines.append(f"- Incrocio: {inter['id']} | Tot_Veicoli:{inter['total_vehicles']}, "
                         f"Tot_Coda:{inter['total_queue']} | Dettaglio: {', '.join(lanes_info)}")
        return "\n".join(lines)

        def _format_metrics_to_text(self, metrics):
        stress = metrics.get("stress_index", 0)"""

    def decide(self, current_metrics, global_directive=None):
        metrics_text = self._format_metrics_to_text(current_metrics)

        if global_directive is None:
            global_directive = {
                "action": "hold_current",
                "target_agent": None,
                "reasoning": "No global directive yet"
            }

        orchestrator_text = ORCHESTRATOR_CONTEXT.format(
            action=global_directive.get("action"),
            target_agent=global_directive.get("target_agent"),
            reasoning=global_directive.get("reasoning"),
        )

        final_prompt = (
            f"{self.static_prompt}\n\n"
            f"{orchestrator_text}\n\n"
            f"{metrics_text}\n\n"
            f"Generate your decision now starting with {{:"
        )

        raw_response = self.brain.think(final_prompt)

        if raw_response is None or raw_response.content is None:
            print(f"\n⚠️ [{self.id}] risposta nulla.")
            return []

        text = raw_response.content.strip()

        print("\n" + "═" * 60)
        print(f"🧠 AGENTE: {self.id}")
        print("📡 RISPOSTA RICEVUTA:")
        print(text)
        print("═" * 60 + "\n")

        text = text.replace("```json", "").replace("```", "").strip()

        try:
            parsed = json.loads(text)

            if isinstance(parsed, dict):
                return [parsed]

            if isinstance(parsed, list):
                return parsed

            return []
        except Exception:
            print(f"⚠️ [{self.id}] JSON non valido: {text}")
            return []