from typing import List
import chromadb
from chromadb.utils import embedding_functions

class VectorContextRetriever:

    def __init__(self, persist_dir: str, collection_name="honeypot_attacks"):
        print(f"--- Apertura RAG DB già esistente ({persist_dir}) ---")

        # Apre un client che punta a un database ChromaDB già indicizzato
        self.client = chromadb.PersistentClient(path=persist_dir)

        # Modello di embedding (necessario per effettuare query sul DB esistente)
        self.emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )

        # Verifica che la collection esista già
        existing = [c.name for c in self.client.list_collections()]
        if collection_name not in existing:
            raise ValueError(
                f"La collection '{collection_name}' non esiste nel DB! "
                f"Collection trovate: {existing}"
            )

        # Apertura della collection esistente (NO creazione!)
        self.collection = self.client.get_collection(
            name=collection_name,
            embedding_function=self.emb_fn
        )

        print(f"--- Collection '{collection_name}' caricata correttamente ---")

    def retrieve(self, current_context_list: List[str], k: int) -> str:

        if not current_context_list:
            return ""

        query_text = " || ".join(current_context_list)

        # Query ai vettori già presenti nel DB
        results = self.collection.query(
            query_texts=[query_text],
            n_results=k
        )

        if not results['ids']:
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

        return formatted_examples