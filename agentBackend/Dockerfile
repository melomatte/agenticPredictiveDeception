# Usiamo un'immagine Python ufficiale, la 3.10 slim è ottima per ChromaDB
FROM python:3.10-slim

# Evita che Python scriva file .pyc su disco e forza i log a stampare subito a schermo
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Installiamo i pacchetti di sistema essenziali per far compilare le librerie C/C++ di ChromaDB
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Impostiamo la directory di lavoro dentro il container
WORKDIR /app

# Copiamo prima il requirements.txt (sfrutta la cache di Docker)
COPY requirements.txt .

# Installiamo le librerie (FastMCP, ChromaDB, Sentence-Transformers)
RUN pip install --no-cache-dir -r requirements.txt

# Copiamo il server MCP all'interno
COPY mcp_server.py .

# Creiamo le cartelle interne per i volumi (che poi verranno sovrascritte dal T9)
RUN mkdir -p /app/data/vector_db /app/data/sessions

# Esponiamo la porta 8000 che userà FastMCP
EXPOSE 8000

# Comando di avvio del server
CMD ["python", "mcp_server.py"]