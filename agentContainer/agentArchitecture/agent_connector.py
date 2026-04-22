import os
from openai import AsyncOpenAI

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
        self.client = AsyncOpenAI(api_key=api_key)

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
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": full_prompt}],
                temperature=0.3, # Bassa per il logger, potremmo alzarla per il falsario
            )
            
            # Estrapolazione risposta e verifica che non sia nulla
            testo_risposta = response.choices[0].message.content
            if not testo_risposta:
                return ""
            else:
                return testo_risposta
            
        except Exception as e:
            print(f"❌ Eccezione API: {e}")
            class Fallback: content = '{"action": "error", "reasoning": "Eccezione API"}'
            return Fallback()