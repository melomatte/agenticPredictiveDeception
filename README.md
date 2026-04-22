# 🕵️ Agentic Predictive Deception

> Un framework di cybersecurity basato su AI che combina tecnologia honeypot con un orchestratore agentico per **predire, osservare e ingannare gli attaccanti** in tempo reale.

---

## 📌 Panoramica

**agenticPredictiveDeception** è un progetto di ricerca in ambito cybersecurity che integra un ambiente honeypot realistico con un agente intelligente capace di rispondere dinamicamente al comportamento degli attaccanti. Analizzando i comandi in tempo reale, il sistema genera risposte false ma contestualmente credibili, prolungando il coinvolgimento dell'attaccante e raccogliendo informazioni di threat intelligence.

Il progetto è composto da due componenti containerizzati e indipendenti che comunicano tramite HTTP:

- **Honeypot** — un servizio SSH simulato che cattura le interazioni degli attaccanti
- **Agent Container** — un orchestratore basato su LLM che predice le intenzioni dell'attaccante e costruisce risposte ingannevoli

---

## 🏗️ Architettura

```
┌─────────────────────────────────────────────────────┐
│                    Attaccante                       │
│           (connessione SSH sulla porta :2222)       │
└──────────────────────┬──────────────────────────────┘
                       │
              ┌────────▼────────┐
              │    Honeypot     │  (container Docker)
              │   Porta: 2222   │  shell SSH simulata
              └────────┬────────┘
                       │ HTTP POST /new_command
                       │ host.docker.internal:8000
              ┌────────▼────────────────┐
              │    Agent Container      │  (host / container)
              │   Orchestratore :8000   │  motore LLM agentico
              └─────────────────────────┘
```

L'honeypot inoltra ogni comando dell'attaccante all'orchestratore, il quale utilizza un LLM per generare una risposta di shell plausibile e ingannevole. Questo crea un ambiente interattivo credibile che mantiene l'attaccante impegnato mentre raccoglie dati comportamentali.

---

## 📁 Struttura del Progetto

```
agenticPredictiveDeception/
├── agentContainer/          # Orchestratore LLM (FastAPI + agente AI)
│   └── ...
├── honeypot/                # Servizio SSH honeypot simulato
│   └── ...
├── docker-compose.yml       # Orchestrazione dei container
└── .gitignore
```

---

## 🚀 Avvio Rapido

### Prerequisiti

- [Docker](https://www.docker.com/) e [Docker Compose](https://docs.docker.com/compose/) installati
- Python 3.10+ (se si esegue l'agente localmente)
- Una chiave API per un LLM (es. OpenAI, Anthropic), se richiesta dalla configurazione dell'agente

### Installazione

```bash
# Clona il repository
git clone https://github.com/melomatte/agenticPredictiveDeception.git
cd agenticPredictiveDeception
```

### Avvio dell'Honeypot (Docker)

L'honeypot gira all'interno di Docker e comunica con l'orchestratore sull'host:

```bash
docker-compose up --build
```

Questo comando:
- Costruisce e avvia il container **honeypot**, esponendo SSH sulla porta `2222`
- Lo connette all'orchestratore tramite `http://host.docker.internal:8000/new_command`

### Avvio dell'Agente (Host)

Avvia l'orchestratore sulla macchina host prima di lanciare Docker:

```bash
cd agentContainer
pip install -r requirements.txt
python main.py  # oppure: uvicorn app:app --port 8000
```

L'agente rimane in ascolto sulla porta `8000` e gestisce gli eventi di comando inviati dall'honeypot.

---

## ⚙️ Configurazione

Il container honeypot è configurato tramite variabili d'ambiente nel file `docker-compose.yml`:

| Variabile | Valore predefinito | Descrizione |
|---|---|---|
| `ORCHESTRATOR_URL` | `http://host.docker.internal:8000/new_command` | Endpoint a cui inviare i comandi dell'attaccante |

Sono applicati limiti di risorse per evitare l'esaurimento dell'host in caso di attacchi aggressivi:

| Risorsa | Limite |
|---|---|
| CPU | 0.50 core |
| Memoria | 512 MB |

---

## 🧠 Come Funziona

1. Un attaccante si connette all'honeypot via SSH sulla porta `2222`
2. Ogni comando inserito viene catturato e inviato all'orchestratore tramite HTTP POST
3. L'agente analizza la sequenza di comandi e predice l'intenzione dell'attaccante (ricognizione, movimento laterale, esfiltrazione di dati, ecc.)
4. Viene generata una risposta falsa ma contestualmente credibile e restituita all'honeypot
5. L'honeypot mostra l'output ingannevole all'attaccante, mantenendo la sessione attiva
6. Tutte le interazioni vengono registrate per l'analisi di threat intelligence

---

## 🔬 Contesto di Ricerca

Questo progetto esplora l'intersezione tra:

- **Cyber Deception** — l'arte di fuorviare gli attaccanti con informazioni false
- **Agentic AI** — sistemi autonomi basati su LLM capaci di ragionamento multi-step
- **Predictive Threat Modeling** — anticipare le mosse dell'attaccante sulla base del comportamento osservato

L'obiettivo è andare oltre i classici honeypot statici verso **ambienti di inganno adattativi e guidati dall'AI**, capaci di operare autonomamente contro minacce reali.

---

## 🛡️ Avvertenza

> Questo strumento è destinato esclusivamente a **scopi di ricerca e didattici**. Distribuirlo solo in ambienti controllati (es. reti di laboratorio isolate, ambienti CTF). Non esporre a infrastrutture di produzione senza una revisione di sicurezza completa. Gli autori non si assumono alcuna responsabilità per un utilizzo improprio.

---

## 🤝 Contribuire

Contributi, segnalazioni di bug e richieste di funzionalità sono benvenuti! Apri pure una issue o invia una pull request.

---

## 📄 Licenza

Questo progetto non specifica attualmente una licenza. Contattare l'autore per informazioni sull'utilizzo.

---

## 👤 Autore

**melomatte** — [Profilo GitHub](https://github.com/melomatte)
