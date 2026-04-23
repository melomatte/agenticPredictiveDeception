import httpx
from agent_connector import AgentConnector
from agent_predictive.predictive_policies import PROMPT_MCP
from google.genai import types
from fastmcp import Client

class PredictiveAgent:
    def __init__(self, mcp_url="http://agent-backend:8000", context_history=5, k=5, model_name="gemini-flash-latest", provider="cloud"):
        self.id = "AGENT PREDICTIVE"
        self.connector = AgentConnector(provider=provider, model_name=model_name)
        self.k=k
        self.context_history=context_history
        self.mcp_url = mcp_url
        self.prompt = PROMPT_MCP.format(k=self.k, N=self.context_history)
        self.tools = self._define_tools()

    def _define_tools(self):
        log_tool = types.FunctionDeclaration(
            name="log_session_event",
            description="Saves the new attacker command to the session log.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "session_id": types.Schema(type=types.Type.STRING, description="Session ID"),
                    "event_dict": types.Schema(type=types.Type.OBJECT, description="The full event dictionary")
                },
                required=["session_id", "event_dict"]
            )
        )
        
        history_tool = types.FunctionDeclaration(
            name="get_session_history",
            description="Get the last N commands of the current session.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "session_id": types.Schema(type=types.Type.STRING, description="Session ID"),
                    "window_size": types.Schema(type=types.Type.INTEGER, description="Number of N commands to get")
                },
                required=["session_id", "window_size"]
            )
        )
        
        rag_tool = types.FunctionDeclaration(
            name="retrieve",
            description="Queries the vector database to find similar past attacks based on current context.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "current_context_list": types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)),
                    "k": types.Schema(type=types.Type.INTEGER)
                },
                required=["current_context_list", "k"]
            )
        )
        return [log_tool, history_tool, rag_tool]

    async def decide(self, eventCommand):
        
        print(f"\n🔮 [{self.id}] Inizio ciclo autonomo per sessione {eventCommand.session_id}...")
        
        # 1. Chiediamo al Connector di aprirci una chat configurata
        chat = await self.connector.create_agentic_chat(
            system_instruction=self.prompt, 
            tools=self.tools
        )

        # 2. Scateniamo l'agente passandogli l'evento puro
        initial_message = f"New event received. Session ID: {eventCommand.session_id}, Command: {eventCommand.cmd}, Full Data: {eventCommand.dict()}"
        response = await chat.send_message(initial_message)

        # 3. IL LOOP DELL'AGENTE (continua finché l'AI non dà il testo finale)
        while response.function_calls:
            tool_responses = []
            
            for function_call in response.function_calls:
                func_name = function_call.name
                args = function_call.args
                
                print(f"🤖 [{self.id}] Tool Calling attivato: chiama '{func_name}'")
                
                # Chiama fisicamente il server MCP Backend via HTTP
                try:
                    tool_result = await self._execute_mcp_call(func_name, args)
                except Exception as e:
                    print(f"❌ [{self.id}] Errore MCP Tool '{func_name}': {e}")
                    tool_result = {"error": str(e)}

                # Prepara la risposta per l'LLM
                tool_responses.append(
                    types.Part.from_function_response(
                        name=func_name,
                        response={"result": tool_result}
                    )
                )
            
            # Rimanda i risultati all'LLM e aspetta la prossima mossa
            response = await chat.send_message(tool_responses)
            
        # 4. Estrazione Predizione Finale
        raw_response = response.text
        candidates = []
        
        if raw_response:
            print(f"✅ [{self.id}] Predizione generata autonomamente:\n{raw_response}")
            candidates = [line.strip() for line in raw_response.splitlines() if line.strip()]
        
        return candidates[:self.k]

    async def _execute_mcp_call(self, tool_name: str, args: dict):
        """Esegue la chiamata usando il vero protocollo MCP (non una semplice POST REST)"""
        # Di default, il trasporto HTTP di FastMCP espone l'API sulla rotta /mcp
        endpoint = f"{self.mcp_url}/mcp" 
        
        # Gestiamo la connessione MCP in modo nativo
        async with Client(endpoint) as client:
            result = await client.call_tool(tool_name, args)
            
            # Convertiamo il risultato in stringa per sicurezza prima di passarlo a Gemini
            return str(result)