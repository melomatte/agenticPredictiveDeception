"""
PredictiveAgent — Agente autonomo per la predizione del prossimo comando dell'attaccante.

Questo modulo implementa un agente AI che, dato un evento (comando SSH intercettato), predice i 'k' comandi più probabili 
che l'attaccante eseguirà come prossimo comando, sfruttando una memoria storica vettoriale (RAG) e il contesto della sessione 
corrente.

PredictiveAgent è un async context manager -> apre una singola connessione SSE (tramite orchestrator) verso il server MCP 
backend all'avvio e la mantiene aperta per tutta la durata del processo, riutilizzandola per ogni tool call. Questo evita 
l'overhead di aprire e chiudere una nuova connessione ad ogni invocazione, che in un sistema ad alta frequenza di eventi 
sarebbe significativo.

Il cuore del modulo è un loop autonomo che delega al modello LLM la scelta di quali tool invocare e in quale ordine, seguendo 
un workflow prestabilito:
    1. log_session_event    → registra il comando corrente nel log di sessione.
    2. get_session_history  → recupera gli ultimi N comandi della sessione (contesto).
    3. retrieve             → interroga il DB vettoriale per trovare attacchi passati simili al contesto corrente (RAG).
    4. [fine tool calls]    → l'LLM genera la predizione finale in testo puro.

Il loop termina quando l'LLM smette di richiedere tool call e produce l'output testuale finale. Due meccanismi di sicurezza 
ne garantiscono la correttezza:
- MAX_ITERATIONS: limite massimo di iterazioni per prevenire loop infiniti.
- REQUIRED_TOOLS: verifica post-loop che tutti e tre i tool obbligatori siano stati effettivamente chiamati prima di 
  accettare la predizione come valida.
"""

from agent_connector import AgentConnector
from agent_forger.forger_policies import PROMPT_MCP
from google.genai import types
from fastmcp import Client
import json

# Parametri per evitare looping e hallucination
MAX_ITERATIONS = 7
REQUIRED_TOOLS = {"get_artifact"}
BACKEND_TOOLS = {"save_artifact", "get_artifact"}
FORGERY_TOOLS = {"deploy_artifact"}

class ForgerAgent:

    def __init__(self, id, mcp_url_backend, mcp_url_forgery,  model_name, provider):
        self.id = f"AGENT FORGER-{id}"
        self.connector = AgentConnector(agent_name=self.id, provider=provider, model_name=model_name)
        self.mcp_url_backend = mcp_url_backend
        self.mcp_url_forgery = mcp_url_forgery
        self.prompt = PROMPT_MCP.format()

        # Definiamo entrambe le rappresentazioni dei tool:
        # - google_tools: usata da GoogleChatWrapper (FunctionDeclaration)
        # - openai_tools: usata da OpenAIChatWrapper (JSON Schema standard)
        # AgentConnector.create_agentic_chat() sceglierà quale usare in base all'sdk configurato.
        self.google_tools, self.openai_tools = self._define_tools()

        # Client MCP inizializzato in __aenter__, None finché l'agente non è attivo
        self._mcp_client_backend: Client | None = None
        self._mcp_client_forgery: Client | None = None

    # --- Gestione ciclo di vita del client MCP ---

    async def __aenter__(self):
        """Apre la connessione SSE una sola volta. Chiamato automaticamente da 'async with'."""
        print(f"[{self.id}] Apertura connessione SSE persistente verso backend:  {self.mcp_url_backend}...")
        self._mcp_client_backend = Client(self.mcp_url_backend)
        await self._mcp_client_backend.__aenter__()
        print(f"[{self.id}] Connessione SSE verso backend aperta con successo.")

        print(f"[{self.id}] Apertura connessione SSE persistente verso forgery (MCP per creazione artefatti da inettare nell'honeypot):  {self.mcp_url_forgery}...")
        self._mcp_client_forgery = Client(self.mcp_url_forgery)
        await self._mcp_client_forgery.__aenter__()
        print(f"[{self.id}] Connessione SSE verso forgery aperta con successo.")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Chiude la connessione SSE. Chiamato automaticamente da 'async with' anche in caso di eccezione."""
        if self._mcp_client_backend:
            print(f"[{self.id}] Chiusura connessione SSE persistente verso backend...")
            await self._mcp_client_backend.__aexit__(exc_type, exc_val, exc_tb)
            self._mcp_client_backend = None
        
        if self._mcp_client_forgery:
            print(f"[{self.id}] Chiusura connessione SSE persistente verso forgery...")
            await self._mcp_client_forgery.__aexit__(exc_type, exc_val, exc_tb)
            self._mcp_client_forgery = None

    # --- Definizione tools MCP ---

    def _define_tools(self):
        """
        Definisce i tool MCP nelle due rappresentazioni richieste dai diversi SDK:
        - Google SDK: FunctionDeclaration con types.Schema
        - OpenAI / OpenRouter / Local: JSON Schema standard (dizionario)
        Entrambe le liste descrivono gli stessi tre tool con gli stessi parametri.
        """

        # 1. FORMATO GOOGLE SDK
        get_artifact_tool = types.FunctionDeclaration(
            name="get_artifact",
            description="Searches the database for an existing fake artifact associated with the predicted command. Returns the JSON artifact if found.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "predicted_command": types.Schema(
                        type=types.Type.STRING, 
                        description="The predicted attacker command to search for."
                    )
                },
                required=["predicted_command"]
            )
        )

        save_artifact_tool = types.FunctionDeclaration(
            name="save_artifact",
            description="Saves a newly generated artifact to the database, associating it with the predicted command.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "predicted_command": types.Schema(
                        type=types.Type.STRING, 
                        description="The predicted attacker command."
                    ),
                    "artifact_data": types.Schema(
                        type=types.Type.OBJECT, 
                        description="The artifact JSON payload containing description, intended_path, and content."
                    )
                },
                required=["predicted_command", "artifact_data"]
            )
        )

        deploy_artifact_tool = types.FunctionDeclaration(
            name="deploy_artifact",
            description="Deploys the generated fake artifact physically into the honeypot file system at the specified path.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "intended_path": types.Schema(
                        type=types.Type.STRING, 
                        description="The realistic Linux path where the artifact should be created (e.g., /var/www/html/config.php)."
                    ),
                    "content": types.Schema(
                        type=types.Type.STRING, 
                        description="The raw textual content of the fake file."
                    )
                },
                required=["intended_path", "content"]
            )
        )
    
        google_tools = [types.Tool(function_declarations=[get_artifact_tool, save_artifact_tool, deploy_artifact_tool])]

        # 2. FORMATO OPENAI / OPENROUTER / LOCAL (JSON Schema standard)
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_artifact",
                    "description": "Searches the database for an existing fake artifact associated with the predicted command. Returns the JSON artifact if found.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "predicted_command": {
                                "type": "string",
                                "description": "The predicted attacker command to search for."
                            }
                        },
                        "required": ["predicted_command"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "save_artifact",
                    "description": "Saves a newly generated artifact to the database, associating it with the predicted command.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "predicted_command": {
                                "type": "string",
                                "description": "The predicted attacker command."
                            },
                            "artifact_data": {
                                "type": "object",
                                "description": "The artifact JSON payload containing description, intended_path, and content."
                            }
                        },
                        "required": ["predicted_command", "artifact_data"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "deploy_artifact",
                    "description": "Deploys the generated fake artifact physically into the honeypot file system at the specified path.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "intended_path": {
                                "type": "string",
                                "description": "The realistic Linux path where the artifact should be created (e.g., /var/www/html/config.php)."
                            },
                            "content": {
                                "type": "string",
                                "description": "The raw textual content of the fake file."
                            }
                        },
                        "required": ["intended_path", "content"]
                    }
                }
            }

        ]

        return google_tools, openai_tools

    # --- Logica predittiva ---

    async def decide(self, predicted_cmd, eventCommand):

        if not self._mcp_client_backend:
            raise RuntimeError(
                f"[{self.id}] Client MCP backend non inizializzato. "
            )
    
        if not self._mcp_client_forgery:
            raise RuntimeError(
                f"[{self.id}] Client MCP forgery non inizializzato. "
            )

        print(f"\n[{self.id}] Inizio ciclo autonomo per sessione {eventCommand.session_id}...")

        # 1. Apriamo la chat configurata: il Connector sceglie il wrapper corretto in base all'sdk
        chat = self.connector.create_agentic_chat(
            system_instruction=self.prompt,
            google_tools=self.google_tools,
            openai_tools=self.openai_tools
        )

        # 2. Messaggio iniziale di avvio della chat
        initial_message = (
            "New event received.\n"
            f"Session ID: {eventCommand.session_id}\n"
            f"Attacker command: {eventCommand.cmd}\n"
            f"Predicted next command: {predicted_cmd}\n"
        )
        response = await chat.send_message(initial_message)

        # Controllo immediato: se l'LLM risponde in testo senza invocare tool, il workflow è fallito
        if not response.function_calls:
            print(f"[{self.id}] L'LLM ha ignorato i tool e ha risposto subito in testo!")
            print(f"[{self.id}] Testo dell'LLM: {response.text}")
            return []

        # 3. Loop agentico
        #
        # Comportamento atteso: il modello chiama i 3 tool in una o più iterazioni,
        # poi produce la predizione finale in testo puro (function_calls vuoto → uscita dal loop).
        #
        # Iterazione 1: function_calls = [log_session_event, get_session_history, retrieve]
        #     → esegui i 3 tool, manda i risultati al modello
        #     → il modello risponde con la predizione in testo
        # Iterazione 2: function_calls = []  → condizione while falsa, si esce
        #
        # In casi meno comuni il modello può chiamare i tool uno alla volta (una iterazione per tool),
        # per questo MAX_ITERATIONS è 7 e non 3.

        called_tools = set()
        iteration = 0

        while response.function_calls and iteration < MAX_ITERATIONS:
            iteration += 1
            tool_responses = []

            for function_call in response.function_calls:
                func_name = function_call.name
                args = function_call.args
                call_id = function_call.id  # None per Google, stringa per OpenAI

                print(f"[{self.id}] Tool Calling (iter {iteration}): chiama '{func_name}'")
                called_tools.add(func_name)
                
                if func_name in BACKEND_TOOLS:
                    endpoint = "backend"
                else:
                    endpoint = "forgery"

                try:
                    tool_result = await self._execute_mcp_call(func_name, args, endpoint)
                except Exception as e:
                    print(f"[{self.id}] Errore MCP Tool '{func_name}': {e}")
                    tool_result = {"error": str(e)}

                # Il Connector formatta la risposta nel formato corretto per il provider attivo
                formatted_response = self.connector.format_tool_response(func_name, tool_result, call_id)
                tool_responses.append(formatted_response)

            response = await chat.send_message(tool_responses)

        # Verifica anti-loop
        if iteration >= MAX_ITERATIONS:
            print(f"[{self.id}] Raggiunto il limite massimo di iterazioni ({MAX_ITERATIONS}). Loop interrotto.")

        # Verifica anti-hallucination: tutti i tool obbligatori devono essere stati chiamati
        missing_tools = REQUIRED_TOOLS - called_tools
        if missing_tools:
            print(f"[{self.id}] Tool obbligatori non chiamati: {missing_tools}. Predizione inaffidabile, annullo.")
            return []

        # 4. Estrazione artefatto finale
        raw_response = response.text
        if not raw_response:
            print(f"⚠️ [{self.id}] Risposta finale vuota/nessun artefatto generato.")
            return []

        raw_response = raw_response.replace("```json", "").replace("```", "").strip()

        try:
            parsed = json.loads(raw_response)
            return parsed
        except Exception:
            print(f"[{self.id}] JSON non valido:\n{raw_response}")
            return []

    async def _execute_mcp_call(self, tool_name: str, args: dict, endpoint: str):
        """Esegue la chiamata MCP riutilizzando la connessione SSE persistente."""
        if endpoint == "forgery":
            result = await self._mcp_client_forgery.call_tool(tool_name, args)
        else:
            result = await self._mcp_client_backend.call_tool(tool_name, args)
        return str(result)