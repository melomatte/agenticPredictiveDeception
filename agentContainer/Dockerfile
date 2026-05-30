FROM python:3.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 1. Impostiamo la root del container
WORKDIR /app

# 2. Installiamo i pacchetti di sistema
RUN apt-get update && \
    apt-get install -y build-essential python3-dev && \
    rm -rf /var/lib/apt/lists/*

# Assumiamo che requirements.txt sia ancora nella cartella principale ai_team/
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Creiamo le cartelle per i mount dei volumi
RUN mkdir -p /app/data/vector_db /app/data/sessions

# 4. Copiamo tutto il contenuto di ai_team/ (inclusa la cartella agentArchitecture) dentro /app
COPY . .

EXPOSE 8000

# --- MODIFICA CHIAVE ---
# 5. Spostiamo il focus di Docker dentro la nuova sottocartella
WORKDIR /app/agentArchitecture

# 6. Avviamo Uvicorn. Ora troverà 'orchestrator.py' nella directory corrente!
CMD ["uvicorn", "honeypot_listener:app", "--host", "0.0.0.0", "--port", "8000"]