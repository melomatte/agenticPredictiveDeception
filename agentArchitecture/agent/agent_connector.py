"""
Motore tecnico (il "Braccio") dell'agente. 
Si occupa esclusivamente dell'interazione di basso livello con l'LLM. Non conosce le regole del traffico; il suo compito è 
garantire che il messaggio arrivi al modello (locale o cloud) e che la risposta torni indietro.
Gestisce: API Keys, Endpoints, Timeouts e Re-try logici.

Presenta 3 funzioni:
    - __init__(self, model_name, provider) = funzione di inizializzazione. Configura il client per comunicare con server locali 
    (LM Studio) o Cloud (LiteLLM Proxy).

    - _load_key_logic(self, filename) = Implementa una logica di ricerca a cascata per la chiave API (file locale o variabile 
    d'ambiente). La chiave viene ricercata (in ordine): root del progetto; Cartella dello script; Variabile d'ambiente

    - think(self, full_prompt): Invia il prompt e monitora lo stato della risposta (motivo del termine, errori API o filtri di sicurezza).
"""

import os
from openai import OpenAI

KEY_FILE = "gemini_key.txt"

class AgentBrain:

    def __init__(self, model_name, provider="local"):
        self.provider = provider
        
        # Configurazione LLM: cloud e locale
        if self.provider == "cloud":
            # Recupero chiave API (file con chiave oppure variabile d'ambiente)
            api_key = self._load_key_logic(KEY_FILE)
            
            # Se la chiave è ancora quella di fallback, blocchiamo tutto con spiegazione
            if api_key == "no-key-found":
                raise ValueError(
                    "\n❌ ERRORE CRITICO: Chiave API non trovata.\n"
                    f"Assicurati che il file '{KEY_FILE}' sia nella root del progetto (o nella cartella agent/) "
                    "o imposta la variabile d'ambiente GEMINI_API_KEY."
                )
            
            # 2. Configurazione endpoint LiteLLM OpenAI-compatible
            base_url = "https://litellm-proxy-1013932759942.europe-west8.run.app"
            self.model = model_name
        else:
            base_url = "http://localhost:1234/v1"
            api_key = "lm-studio"
            self.model = "local-model"

        self.client = OpenAI(base_url=base_url, api_key=api_key)

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

    def think(self, full_prompt):
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": full_prompt}],
                temperature=0.0,
            )
            
            # Valutazione stato risposta ricevuta (se è safety -> filtri sicurezza)
            print("\n🔍 --- ISPEZIONE RISPOSTA API ---")
            print(f"ID Risposta: {response.id}")
            finish_reason = response.choices[0].finish_reason
            print(f"Motivo termine (finish_reason): {finish_reason}")

            return response.choices[0].message
        except Exception as e:
            print(f"❌ Eccezione API: {e}")
            class Fallback: content = '{"action": "error", "reasoning": "Eccezione API"}'
            return Fallback()