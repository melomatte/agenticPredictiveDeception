import os
import json
from typing import List
from collections import deque
from fastmcp import FastMCP
import chromadb
from chromadb.utils import embedding_functions

# Configurazione percorsi (interni al container backend)
DB_PATH = "/app/data/vector_db"
LOG_PATH = "/app/data/sessions"

# Inizializzazione MCP Server
mcp = FastMCP("Agent-Backend")
print("🚀 [BACKEND] Avvio del server Agent-Backend...")

# --- Inizializzazione ChromaDB ---
print(f"📂 [BACKEND] Connessione a ChromaDB in {DB_PATH}...")
emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
db_client = chromadb.PersistentClient(path=DB_PATH)

try:
    collection = db_client.get_collection(name="honeypot_attacks", embedding_function=emb_fn)
    print("✅ [BACKEND] Collection 'honeypot_attacks' caricata con successo.")
except Exception as e:
    print("❌ [BACKEND] ERRORE: Collection 'honeypot_attacks' non trovata. Hai eseguito lo script di indicizzazione?")
    raise e

@mcp.tool()
def retrieve(current_context_list: List[str], k: int) -> str:
    """Interroga il DB vettoriale e restituisce attacchi passati simili."""
    print(f"\n🔍 [BACKEND][RAG] Ricevuta richiesta di Retrieve. Contesto attuale ({len(current_context_list)} comandi).")
    
    if not current_context_list: 
        print("⚠️ [BACKEND][RAG] Contesto vuoto, annullo la ricerca.")
        return ""

    query_text = " || ".join(current_context_list)
    print(f"🧠 [BACKEND][RAG] Ricerca vettori per: '{query_text}'")

    # Query ai vettori già presenti nel DB
    results = collection.query(
        query_texts=[query_text],
        n_results=k
    )

    if not results['ids'] or len(results['ids'][0]) == 0:
        print("📭 [BACKEND][RAG] Nessun risultato simile trovato nel database.")
        return ""

    # Estrazione dati
    ids = results['ids'][0]
    docs = results['documents'][0]
    metas = results['metadatas'][0]

    formatted_examples = ""

    for i in range(len(ids)):
        hist_ctx = docs[i].replace(" || ", "\n")
        hist_next = metas[i]['next_command']

        formatted_examples += (
            f"--- SIMILAR PAST ATTACK (Example {i+1}) ---\n"
            f"Context:\n{hist_ctx}\n"
            f"Attacker Next Move:\n{hist_next}\n\n"
        )

    print(f"🎯 [BACKEND][RAG] Trovati {len(ids)} esempi storici. Restituisco i dati all'Agente.")
    return formatted_examples

@mcp.tool()
def log_session_event(session_id: str, event_data: dict) -> bool:
    """Salva un nuovo comando nel file di log della sessione"""
    print(f"\n📝 [BACKEND][LOG] Ricevuto nuovo evento per la sessione: {session_id}")
    
    os.makedirs(LOG_PATH, exist_ok=True)
    file_path = os.path.join(LOG_PATH, f"session_{session_id}.jsonl")
    
    with open(file_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(event_data) + '\n')
        
    print(f"💾 [BACKEND][LOG] Evento scritto con successo in {file_path}")
    return True

@mcp.tool()
def get_session_history(session_id: str, window_size: int) -> list:
    """Recupera gli ultimi N comandi dal file di sessione specificato"""
    print(f"\n📖 [BACKEND][LOG] Lettura ultimi {window_size} comandi per sessione: {session_id}")
    
    file_path = os.path.join(LOG_PATH, f"session_{session_id}.jsonl")
    
    if not os.path.exists(file_path): 
        print("⚠️ [BACKEND][LOG] File di sessione non ancora esistente. Restituisco lista vuota.")
        return []
    
    context_history = []
    with open(file_path, 'r', encoding='utf-8') as f:
        last_lines = deque(f, maxlen=window_size)
    
        for line in last_lines:
            if line.strip():
                try:
                    parsed_line = json.loads(line)
                    if 'cmd' in parsed_line:
                        context_history.append(parsed_line['cmd'])
                except json.JSONDecodeError:
                    continue
                    
    print(f"✅ [BACKEND][LOG] Letti {len(context_history)} comandi storici.")
    return context_history

if __name__ == "__main__":
    print("🌐 [BACKEND] MCP Server in ascolto. Pronto a servire gli agents sulla porta 8000...")
    mcp.run(transport="http",host="0.0.0.0", port=8000)