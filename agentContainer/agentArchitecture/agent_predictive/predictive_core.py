from collections import deque
import json
import os
from agent_connector import AgentConnector
from agent_predictive.predictive_policies import PREDICTIVE_STATIC, RAG_EXAMPLE
from agent_predictive.rag_support import VectorContextRetriever

class PredictiveAgent:
    def __init__(self, rag_dir, session_output_path, context_history=5, k=5, model_name="gemini-flash-latest", provider="cloud"):
        self.id = "AGENT PREDICTIVE"
        self.connector = AgentConnector(provider=provider, model_name=model_name)
        self.rag = VectorContextRetriever(rag_dir)
        self.k=k
        self.context_history=context_history
        self.session_output_path=session_output_path
        #self.mcp_url = os.getenv("MCP_SERVER_URL", "http://mcp-server:8000")

    async def decide(self, eventCommand, global_directive=None):
        
        session_file = os.path.join(self.session_output_path, f"session_{eventCommand.session_id}.jsonl")

        # 1. CREAZIONE CONTEXT HISTORY -> Lettura dei context_history-1 comandi per la creazione del context di attacco
        context_history = []

        if os.path.exists(session_file):
            with open(session_file, 'r', encoding='utf-8') as f:
                last_lines = deque(f, maxlen=self.context_history - 1)
                
                for line in last_lines:
                    if line.strip():
                        parsed_line = json.loads(line)
                        
                        if 'cmd' in parsed_line:
                            context_history.append(parsed_line['cmd'])

        # Aggiungiamo del comando corrente alla finestra di attacco
        context_history.append(eventCommand.cmd)

        # 2. LOGGING NUOVO COMANDO -> Logging del nuovo comando ricevuto nel file .jsonl di sessione
        current_event_dict = eventCommand.dict()
        with open(session_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(current_event_dict) + '\n')
            
        print(f"📝 [{self.id}] Log salvato. Contesto LLM aggiornato a {len(context_history)} comandi puri.")

        # 3. RAG -> retrieve all'interno del DB vettoriale
        rag_example = self.rag.retrieve(context_history, self.k)
        
        # 4. COSTRUZIONE PROMPT FINALE
        final_prompt = (
            f"{PREDICTIVE_STATIC.format(k=self.k)}\n"
            f"\n{RAG_EXAMPLE.format(rag=rag_example)}\n"
            f"\nCURRENT SESSION HISTORY:\n{context_history}\n"
            f"PREDICT NEXT {self.k} COMMANDS (Raw text only):"
        ).strip()

        # 5. CHIAMATA LLM -> chiamata LLM con il prompt costruito e restituizione dei K comandi predetti
        raw_response = await self.connector.think(final_prompt)
        
        candidates = []
        if raw_response:
            print(f"[{self.id}] Risposta della predizione ottenuta correttamente\n")
            candidates = [line.strip() for line in raw_response.splitlines() if line.strip()]
        else: 
            print(f"[{self.id}] Risposta della predizione vuota\n")

        return candidates[:self.k]