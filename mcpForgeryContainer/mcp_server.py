import os
import docker
import tarfile
import io
import time
from fastmcp import FastMCP

# Inizializzazione MCP Server
mcp = FastMCP("Forgery")
print("[MCP FORGERY] Avvio del MCP server forgery...")

# Inizializza il client Docker (leggerà automaticamente dal docker.sock)
docker_client = docker.from_env()

HONEYPOT_CONTAINER_NAME = "agenticpredictivedeception-honeypot-1"

@mcp.tool()
def deploy_artifact(intended_path: str, content: str) -> str:
    """
    Inietta fisicamente un file di testo all'interno dell'Honeypot 
    senza che l'Honeypot debba autorizzare l'operazione.
    """
    print(f"\n[MCP FORGERY] Iniezione artefatto in: {intended_path}")
    
    try:
        # 1. Recuperiamo l'istanza del container Honeypot
        honeypot = docker_client.containers.get(HONEYPOT_CONTAINER_NAME)
        
        # 2. Prepariamo il percorso
        file_name = os.path.basename(intended_path)
        dir_name = os.path.dirname(intended_path)
        
        # 3. Creiamo un archivio TAR direttamente in memoria RAM (zero scritture su disco!)
        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode='w') as tar:
            # Creiamo i metadati del file
            tarinfo = tarfile.TarInfo(name=file_name)
            tarinfo.size = len(content.encode('utf-8'))
            tarinfo.mtime = int(time.time())
            
            # Inseriamo il contenuto nel file virtuale
            tar.addfile(tarinfo, io.BytesIO(content.encode('utf-8')))
        
        # Riportiamo il "cursore" del file in memoria all'inizio
        tar_stream.seek(0)
        
        # 4. Magia Nera di Docker: iniettiamo l'archivio direttamente nella cartella di destinazione!
        # Equivalente API di 'docker cp'
        honeypot.put_archive(path=dir_name, data=tar_stream)
        
        print(f"[MCP FORGERY] Artefatto creato con successo in {intended_path}")
        return (
            "SUCCESS: The file has been physically created in the honeypot. "
            "CRITICAL INSTRUCTION: DO NOT call any more tools. "
        )
        
    except docker.errors.NotFound:
        print(f"[MCP FORGERY] ERRORE: Container honeypot '{HONEYPOT_CONTAINER_NAME}' non trovato!")
        return f"ERROR: Failed to deploy artifact. Reason: container didn't find"
    except Exception as e:
        print(f"[MCP FORGERY] ERRORE di iniezione: {e}")
        return f"ERROR: Failed to deploy artifact. Reason: {str(e)}"

if __name__ == "__main__":
    print("[MCP FORGERY] MCP Server in ascolto. Pronto a servire gli agents sulla porta 8000...")
    mcp.run(transport="sse",host="0.0.0.0", port=8000)