import os
from google.genai.types import HarmCategory, HarmBlockThreshold, GenerateContentConfig
from google.genai import Client

KEY_FILE = "api_key.txt"

class AgentConnector:
    def __init__(self, model_name="gemini-flash-latest", provider="cloud"):
        self.provider = provider
        
        if self.provider == "cloud":
            api_key = self._load_key_logic(KEY_FILE)
            if api_key == "no-key-found":
                raise ValueError(
                    "\n❌ ERRORE CRITICO: Chiave API non trovata.\n"
                    f"Assicurati che il file '{KEY_FILE}' sia nella root del progetto"
                    "o imposta la variabile d'ambiente GEMINI_API_KEY."
                )
            self.model = model_name
        else:
            base_url = "http://localhost:1234/v1"
            api_key = "lm-studio"
            self.model = "local-model"

        # Usiamo AsyncOpenAI per non bloccare i thread di FastAPI
        self.client = Client(api_key=api_key)

    def _load_key_logic(self, filename):
        
        # 1. Root del progetto
        path_root = os.path.abspath(filename)
        
        # 2. Cartella dello script (ricerca del file all'interno della cartella agent/)
        path_agent = os.path.abspath(os.path.join(os.path.dirname(__file__), filename))
        
        for path in [path_root, path_agent]:
            if os.path.exists(path):
                with open(path, "r") as f:
                    key = f.read().strip()
                    if key:
                        print(f"✅ Chiave API caricata con successo da: {path}")
                        return key
        
        # 3. Variabile d'ambiente come GEMINI_API_KEY
        env_key = os.getenv("GEMINI_API_KEY")
        if env_key:
            print("✅ Chiave API caricata dalla variabile d'ambiente.")
            return env_key
            
        return "no-key-found"

    async def think(self, full_prompt):
        try:
            #Visto che stiamo simulando degli attacchi, è necessario disattivare i blocchi di sicurezza
            safety_config = [
                {"category": HarmCategory.HARM_CATEGORY_HATE_SPEECH, "threshold": HarmBlockThreshold.BLOCK_NONE},
                {"category": HarmCategory.HARM_CATEGORY_HARASSMENT, "threshold": HarmBlockThreshold.BLOCK_NONE},
                {"category": HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, "threshold": HarmBlockThreshold.BLOCK_NONE},
                {"category": HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, "threshold": HarmBlockThreshold.BLOCK_NONE},
            ]

            response = self.client.models.generate_content(
                model=self.model,
                contents=full_prompt,
                config={
                    "temperature": 0.0,
                    "top_p": 0.1,
                    "max_output_tokens": 1024,
                    "safety_settings": safety_config # APPLICHIAMO I FILTRI PERMISSIVI
                }
            )

            # Controllo difensivo: se il modello restituisce None o non ha testo
            if not response or not response.text: return ""
            else: return response.text
            
        except Exception as e:
            print(f"❌ Eccezione API: {e}")
            class Fallback: content = '{"action": "error", "reasoning": "Eccezione API"}'
            return Fallback()
    
    def create_agentic_chat(self, system_instruction: str, tools: list):
        """Crea una sessione interattiva con l'LLM, equipaggiata con Tool"""
        
        safety_config = [
            {"category": HarmCategory.HARM_CATEGORY_HATE_SPEECH, "threshold": HarmBlockThreshold.BLOCK_NONE},
            {"category": HarmCategory.HARM_CATEGORY_HARASSMENT, "threshold": HarmBlockThreshold.BLOCK_NONE},
            {"category": HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, "threshold": HarmBlockThreshold.BLOCK_NONE},
            {"category": HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, "threshold": HarmBlockThreshold.BLOCK_NONE},
        ]

        config = GenerateContentConfig(
            system_instruction=system_instruction,
            tools=tools,
            temperature=0.0, # Bassissima per seguire le istruzioni rigidamente
            safety_settings=safety_config
        )

        # Restituiamo la sessione di chat aperta
        return self.client.aio.chats.create(
            model=self.model,
            config=config
        )