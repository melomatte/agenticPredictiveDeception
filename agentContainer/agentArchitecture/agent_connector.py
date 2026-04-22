import os
from openai import AsyncOpenAI

class AgentConnector:
    def __init__(self, model_name="gpt-4o-mini", provider="cloud"):
        self.provider = provider
        
        if self.provider == "cloud":
            api_key = self._load_key_logic(".env")
            if api_key == "no-key-found":
                print("❌ ERRORE CRITICO: Chiave API non trovata nel .env")
            self.model = model_name
        else:
            # Per futuri modelli locali
            api_key = "lm-studio"
            self.model = "local-model"

        # Usiamo AsyncOpenAI per non bloccare i thread di FastAPI
        self.client = AsyncOpenAI(api_key=api_key)

    def _load_key_logic(self, filename):
        path_root = os.path.abspath(filename)
        path_agent = os.path.abspath(os.path.join(os.path.dirname(__file__), filename))
        
        for path in [path_root, path_agent]:
            if os.path.exists(path):
                with open(path, "r") as f:
                    for line in f:
                        if line.startswith("OPENAI_API_KEY="):
                            return line.split("=", 1)[1].strip()
        
        env_key = os.getenv("OPENAI_API_KEY")
        if env_key:
            return env_key
            
        return "no-key-found"

    async def think(self, full_prompt):
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": full_prompt}],
                temperature=0.3, # Bassa per il logger, potremmo alzarla per il falsario
            )
            return response.choices[0].message
        except Exception as e:
            print(f"❌ Eccezione API: {e}")
            class Fallback: content = '{"action": "error", "reasoning": "Eccezione API"}'
            return Fallback()