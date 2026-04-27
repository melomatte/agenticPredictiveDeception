"""
AgentConnector — Interfaccia unificata verso il modello LLM (Google Gemini / OpenAI / OpenRouter / Locale).

Questo modulo astrae la comunicazione con il modello linguistico, esponendo due modalità di interazione distinte a 
seconda del tipo di task richiesto.

METODO think():
Chiamata singola stateless (single-turn): invia un prompt e riceve una risposta. Adatta per task semplici che non 
richiedono memoria della conversazione né l'uso di tool esterni. Non supporta il tool calling loop.
Supporta sia Google SDK (aio) che OpenAI SDK, selezionando automaticamente il percorso corretto in base all'sdk 
configurato, senza mai bloccare l'event loop.

METODO create_agentic_chat():
Crea e restituisce una sessione di chat multi-turno configurata con un system prompt e un set di tool.
Questa è la modalità corretta per implementare agenti autonomi con tool calling, per due motivi fondamentali:
    1. STATO CONVERSAZIONALE: la sessione di chat mantiene automaticamente l'intera cronologia dei messaggi 
       (prompt → tool call → tool result → ...) lato SDK, senza che il chiamante debba ricostruirla manualmente.
    2. TOOL CALLING NATIVO: il formato dei messaggi tool_use e tool_result viene gestito correttamente dall'SDK,
       che si aspetta una struttura specifica per alternare risposte del modello e risultati dei tool. Gestirla 
       manualmente con generate_content() sarebbe fragile e soggetto a errori di formato.

La sessione restituita viene poi pilotata dal loop agentico in PredictiveAgent, che invia i risultati dei tool con 
chat.send_message() fino a quando il modello non produce la risposta testuale finale.

CONFIGURAZIONE TRAMITE FILE CHIAVE:
Il file api_key.txt deve contenere due righe nel formato:
    <api_key>
    sdk=<google|openai|openrouter>
L'attributo 'provider' distingue invece tra modalità 'cloud' (legge il file) e 'local' (LM Studio via OpenAI compat.).
"""

import os
import json
from google.genai.types import HarmCategory, HarmBlockThreshold, GenerateContentConfig, Part
from google.genai import Client as GoogleClient
from openai import AsyncOpenAI

KEY_FILE = "api_key_openrouter.txt"

# SDK validi accettati nel file di configurazione
VALID_SDKS = {"google", "openai", "openrouter"}

# --- CLASSI DI UNIFORMAZIONE (ADAPTER PATTERN) ---

class UnifiedFunctionCall:
    """Oggetto standardizzato per le chiamate ai tool, indipendente dal provider."""
    def __init__(self, name, args, call_id=None):
        self.name = name
        self.args = args
        # call_id è usato solo da OpenAI per collegare tool_result al tool_call.
        # Per Google è sempre None: Part.from_function_response non richiede un id.
        self.id = call_id

class UnifiedResponse:
    """Risposta standardizzata restituita al PredictiveAgent, indipendente dal provider."""
    def __init__(self, text="", function_calls=None):
        self.text = text
        self.function_calls = function_calls or []


# --- WRAPPERS PER LE SESSIONI DI CHAT ---

class GoogleChatWrapper:
    def __init__(self, google_chat):
        self.chat = google_chat

    async def send_message(self, message):
        response = await self.chat.send_message(message)

        text = response.text or ""
        function_calls = []
        if response.function_calls:
            for fc in response.function_calls:
                # Google non espone un call_id: passiamo None esplicitamente (vedi UnifiedFunctionCall)
                function_calls.append(UnifiedFunctionCall(name=fc.name, args=fc.args, call_id=None))

        return UnifiedResponse(text, function_calls)

class OpenAIChatWrapper:
    def __init__(self, client, model, system_instruction, tools):
        self.client = client
        self.model = model
        self.tools = tools
        self.history = [{"role": "system", "content": system_instruction}]

    async def send_message(self, message):
        # 1. Aggiunge il messaggio utente o i risultati dei tool alla cronologia
        if isinstance(message, str):
            self.history.append({"role": "user", "content": message})
        elif isinstance(message, list):
            if not message:
                raise ValueError("Lista tool_responses vuota passata a send_message: nessun tool result da inviare.")
            # I tool results sono già formattati da AgentConnector.format_tool_response
            for tool_result in message:
                self.history.append(tool_result)

        # 2. Prepara la chiamata
        kwargs = {"model": self.model, "messages": self.history, "temperature": 0.0}
        if self.tools:
            kwargs["tools"] = self.tools

        # 3. Esegue la chiamata API
        response = await self.client.chat.completions.create(**kwargs)
        msg = response.choices[0].message

        # 4. Aggiunge la risposta dell'assistente alla history (obbligatorio per OpenAI:
        #    il messaggio con tool_calls deve precedere i tool results nel turno successivo)
        self.history.append(msg)

        # 5. Estrae testo e tool call in formato unificato
        text = msg.content or ""
        function_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                # OpenAI restituisce gli argomenti come stringa JSON: deserializziamo
                args = json.loads(tc.function.arguments)
                function_calls.append(UnifiedFunctionCall(name=tc.function.name, args=args, call_id=tc.id))

        return UnifiedResponse(text, function_calls)


# --- AGENT CONNECTOR ---

class AgentConnector:

    def __init__(self, model_name="models/gemini-2.0-flash-lite-001", provider="cloud"):
        self.provider = provider

        if self.provider == "local":
            # Modalità locale: LM Studio espone un'API compatibile OpenAI.
            # In contesto Docker, 'localhost' punta al container stesso, non all'host:
            # 'host.docker.internal' è l'indirizzo speciale per raggiungere la rete dell'host.
            print("🏠 [CONNECTOR] Inizializzazione in modalità LOCALE (LM Studio)")
            self.sdk = "openai"
            self.client = AsyncOpenAI(base_url="http://host.docker.internal:1234/v1", api_key="lm-studio")
            self.model = model_name
            print(f"✅ [CONNECTOR] Connettore locale inizializzato (Modello: {self.model})")

        else:
            # Modalità cloud: legge chiave e sdk dal file di configurazione
            api_key, self.sdk = self._load_key_logic(KEY_FILE)

            if self.sdk == "google":
                self.client = GoogleClient(api_key=api_key)
                self.model = model_name
                print(f"✅ [CONNECTOR] Connettore inizializzato su Google SDK (Modello: {self.model})")

            elif self.sdk == "openai":
                self.client = AsyncOpenAI(api_key=api_key, base_url="https://api.openai.com/v1")
                self.model = model_name
                print(f"✅ [CONNECTOR] Connettore inizializzato su OpenAI SDK (Modello: {self.model})")

            elif self.sdk == "openrouter":
                # OpenRouter accetta il formato google/gemini-* invece di models/gemini-*
                self.client = AsyncOpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")
                self.model = model_name.replace("models/", "google/") if "gemini" in model_name else model_name
                print(f"✅ [CONNECTOR] Connettore inizializzato su OpenRouter (Modello: {self.model})")

    def _load_key_logic(self, filename) -> tuple[str, str]:
        """
        Legge il file di configurazione della chiave API.
        
        Formato atteso del file (due righe):
            <api_key>
            sdk=<google|openai|openrouter>

        Ordine di ricerca: root del progetto → cartella dello script → variabili d'ambiente.
        Le variabili d'ambiente attese sono LLM_API_KEY e LLM_SDK.
        
        Returns:
            (api_key, sdk) come tupla di stringhe.
        
        Raises:
            ValueError: se chiave o sdk non vengono trovati o sdk non è valido.
        """
        path_root = os.path.abspath(filename)
        path_agent = os.path.abspath(os.path.join(os.path.dirname(__file__), filename))

        for path in [path_root, path_agent]:
            if os.path.exists(path):
                with open(path, "r") as f:
                    lines = [l.strip() for l in f.readlines() if l.strip()]

                if len(lines) < 2:
                    raise ValueError(
                        f"❌ [CONNECTOR] Il file '{path}' deve contenere due righe:\n"
                        "  Riga 1: <api_key>\n"
                        "  Riga 2: sdk=<google|openai|openrouter>"
                    )

                api_key = lines[0]
                sdk_line = lines[1]

                if not sdk_line.startswith("sdk="):
                    raise ValueError(
                        f"❌ [CONNECTOR] Riga 2 del file '{path}' non valida: '{sdk_line}'.\n"
                        "  Formato atteso: sdk=<google|openai|openrouter>"
                    )

                sdk = sdk_line.split("=", 1)[1].strip().lower()

                if sdk not in VALID_SDKS:
                    raise ValueError(
                        f"❌ [CONNECTOR] SDK '{sdk}' non riconosciuto. Valori accettati: {VALID_SDKS}"
                    )

                print(f"✅ [CONNECTOR] Configurazione caricata da: {path} (sdk={sdk})")
                return api_key, sdk

        # Fallback: variabili d'ambiente
        env_key = os.getenv("LLM_API_KEY")
        env_sdk = os.getenv("LLM_SDK", "").strip().lower()

        if env_key and env_sdk in VALID_SDKS:
            print(f"✅ [CONNECTOR] Configurazione caricata da variabili d'ambiente (sdk={env_sdk})")
            return env_key, env_sdk

        raise ValueError(
            "❌ [CONNECTOR] Impossibile caricare la configurazione API.\n"
            f"  Opzione 1: crea il file '{filename}' con chiave e sdk=<google|openai|openrouter>.\n"
            "  Opzione 2: imposta le variabili d'ambiente LLM_API_KEY e LLM_SDK."
        )

    async def think(self, full_prompt) -> str:
        """Chiamata singola stateless al modello. Usa il client asincrono corretto per il provider."""
        try:
            if self.sdk == "google":
                # Usiamo il client asincrono (aio) per non bloccare l'event loop
                response = await self.client.aio.models.generate_content(
                    model=self.model,
                    contents=full_prompt,
                    config={"temperature": 0.0, "top_p": 0.1, "max_output_tokens": 1024}
                )
                return response.text if response and response.text else ""

            else:
                # openai / openrouter / local: tutti compatibili con AsyncOpenAI
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": full_prompt}],
                    temperature=0.0,
                    max_tokens=1024
                )
                return response.choices[0].message.content or ""

        except Exception as e:
            print(f"❌ [CONNECTOR] Eccezione in think(): {e}")
            return ""

    def create_agentic_chat(self, system_instruction: str, google_tools: list, openai_tools: list):
        """Restituisce la sessione di chat wrappata nel formato unificato per il provider corrente."""
        if self.sdk == "google":
            config = GenerateContentConfig(
                system_instruction=system_instruction,
                tools=google_tools,
                temperature=0.0
            )
            chat = self.client.aio.chats.create(model=self.model, config=config)
            return GoogleChatWrapper(chat)
        else:
            # openai / openrouter / local: tutti usano OpenAIChatWrapper
            return OpenAIChatWrapper(self.client, self.model, system_instruction, openai_tools)

    def format_tool_response(self, name: str, result: str, call_id: str = None):
        """
        Formatta il risultato di un tool nel formato richiesto dal provider corrente.
        
        Google: Part.from_function_response (call_id non necessario)
        OpenAI/OpenRouter/Local: dizionario con role='tool' e tool_call_id (obbligatorio per OpenAI)
        """
        if self.sdk == "google":
            return Part.from_function_response(name=name, response={"result": result})
        else:
            return {
                "role": "tool",
                "tool_call_id": call_id,
                "name": name,
                "content": json.dumps({"result": result})
            }