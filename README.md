# 🕵️ Agentic Predictive Deception

> Un framework di cybersecurity basato su AI che combina tecnologia honeypot con un sistema agentico multi-LLM per **predire, preparare e iniettare artefatti ingannevoli** in risposta al comportamento degli attaccanti in tempo reale.

---

## Indice

- [Panoramica](#panoramica)
- [Architettura del Sistema](#architettura-del-sistema)
- [Componenti e Funzionamento](#componenti-e-funzionamento)
  - [1. Honeypot Container](#1-honeypot-container)
  - [2. Agentic System Container](#2-agentic-system-container)
  - [3. Backend Container](#3-backend-container)
  - [4. MCP Forgery Container](#4-mcp-forgery-container)
- [Flusso di Esecuzione End-to-End](#flusso-di-esecuzione-end-to-end)
- [Architettura Agentica Interna](#architettura-agentica-interna)
  - [AgentConnector](#agentconnector)
  - [PredictiveAgent](#predictiveagent)
  - [ForgerAgent](#forgeragent)
  - [HoneypotListener (Orchestratore)](#honeypotlistener-orchestratore)
- [Protocollo MCP (Model Context Protocol)](#protocollo-mcp-model-context-protocol)
- [Struttura del Progetto](#struttura-del-progetto)
- [Configurazione e Avvio](#configurazione-e-avvio)
- [Punti Fondamentali di Design](#punti-fondamentali-di-design)
- [Contesto di Ricerca](#contesto-di-ricerca)

---

## Panoramica

**agenticPredictiveDeception** è un sistema di cyber deception adattivo che va oltre i classici honeypot statici. Quando un attaccante si connette via SSH e digita un comando, il sistema non si limita a registrarlo: attiva una pipeline AI multi-agente che **predice il prossimo comando** dell'attaccante e **prepara proattivamente file falsi ma credibili** già presenti nel filesystem dell'honeypot prima che vengano cercati.

Il risultato è un ambiente ingannevole dinamico, capace di adattarsi al comportamento specifico di ogni attaccante in tempo reale.

**agenticPredictiveDeception** è l'evoluzione agentica di [**Predictive Deception: LLM-based Command Anticipation in SSH Honeypots**](https://github.com/BlackRaffo70/Predictive_deception), progetto sviluppato nell'ambito del corso di Laurea Magistrale in Ingegneria Informatica all'**Università di Bologna**. 

Il progetto originale ha stabilito le fondamenta concettuali e tecniche del sistema:

- un honeypot SSH con **fakeshell** realistica
- un motore di predizione **RAG + LLM** valutato su dataset reali di attacchi (CyberLab Honeynet via Zenodo)
- un modulo **Defender** che predice i prossimi comandi e genera artefatti nel filesystem della VM

Questo repository riprende quell'architettura e la trasforma in un **sistema multi-agente containerizzato**, introducendo:

| Aspetto | Progetto originale | Questa estensione |
|---|---|---|
| Deployment | VM Vagrant + Ansible | Docker Compose (4 container) |
| Coordinamento | Script monolitico (`defender.py`) | Pipeline multi-agente asincrona (PredictiveAgent + pool di ForgerAgent) |
| Comunicazione LLM↔tool | Chiamate dirette in-process | Protocollo MCP via SSE (FastMCP) |
| Iniezione artefatti | Scrittura file nella VM | Docker API (`put_archive`) sul container honeypot |
| Provider LLM | Gemini / Ollama (locale) | Astratto: Google, OpenAI, OpenRouter, LM Studio |
| Parallelismo forgery | Sequenziale | `k` ForgerAgent in parallelo, uno per predizione |

Il database vettoriale ChromaDB e il corpus di attacchi storici originati dal progetto precedente sono riutilizzati direttamente come volume bind del container `backend`.

## Architettura del Sistema

Il sistema è composto da **quattro container Docker** che comunicano su due reti interne distinte:

```
┌──────────────────────────────────────────────┐
│                  ATTACCANTE                  │
│           (SSH sulla porta 2222)             │
└───────────────────┬──────────────────────────┘
                    │ SSH
        ┌───────────▼────────────┐
        │        honeypot        │  (honeypot_net)
        │       Porta: 2222      │  fakeshell.py
        └───────────┬────────────┘
                    │ HTTP POST /new_command        ▲
                    │                               │ docker cp
        ┌───────────▼────────────┐      ┌───────────┴──────────┐
        │    agentic-system      │─────▶│     mcp-forgery      │
        │  (honeypot_net +       │ SSE  │    (honeypot_net)    │
        │   backend_net)         │      │     Docker API       │
        │  FastAPI + agenti LLM  │      └──────────────────────┘
        └───────────┬────────────┘
                    │ SSE (MCP)
        ┌───────────▼────────────┐
        │        backend         │  (backend_net)
        │    ChromaDB + Log      │
        └────────────────────────┘
```

**Reti Docker:**
- `honeypot_net`: connette honeypot, agentic-system e mcp-forgery. È la rete "operativa" dell'inganno.
- `backend_net`: connette agentic-system e backend. Isola i dati storici (RAG, sessioni, artefatti).

---

## Componenti e Funzionamento

### 1. Honeypot Container

**Directory:** `honeypotContainer/`  
**Immagine base:** Python 3.10 + OpenSSH Server

Il container espone un server SSH realistico sulla porta `2222`. Quando un attaccante si connette, viene presentata una shell Ubuntu 22.04 simulata. Infatti, l'utente `honeypot` ha come shell di login direttamente `fakeshell.py`.

**`fakeshell.py`** è il cuore dell'honeypot. Per ogni comando digitato dall'attaccante:

1. Genera un `SESSION_ID` univoco nel formato `YYYY-MM-DD_IP`.
2. Chiama `trigger_ai()` in modo non bloccante per notificare al container agentico l'inizio del reasoning.
3. Esegue il comando **realmente** all'interno del container, mostrando l'output autentico del sistema.

Il punto chiave è che la shell esegue comandi reali sul container (un sistema Linux ridotto ma funzionante), rendendo l'esperienza dell'attaccante autentica, mentre l'AI lavora in background per preparare i file che l'attaccante troverà quando eseguirà il prossimo comando (se esegue uno dei comandi predetti).

---

### 2. Agentic System Container

**Directory:** `agentContainer/`  
**Immagine base:** Python 3.10 slim  
**Porta:** 8000 (HTTP/FastAPI)

È il cervello del sistema. Espone un endpoint FastAPI `POST /new_command` che riceve gli eventi dalla fakeshell e coordina il lavoro dei due tipi di agenti AI.

Il container si configura tramite variabili d'ambiente:

| Variabile | Descrizione |
|-----------|-------------|
| `PROVIDER` | `cloud` (legge API key da secret) o `local` (LM Studio) |
| `MODEL_NAME` | Nome del modello LLM (es. `deepseek/deepseek-v4-flash`) |
| `BACKEND_MCP_URL` | URL SSE del backend (`http://backend:8000/sse`) |
| `FORGERY_MCP_URL` | URL SSE del forgery (`http://mcp-forgery:8000/sse`) |
| `NUM_PREDICTION` | Numero `k` di comandi da predire per ogni evento |

La chiave API e l'SDK vengono passati tramite **Docker secret** (file `.env` montato in `/run/secrets/llm_config_secret`), mai come variabili d'ambiente in chiaro.

---

### 3. Backend Container

**Directory:** `backendContainer/`  
**Immagine base:** Python 3.10 slim  
**Porta:** 8000 (MCP/SSE)

Espone un server MCP (Model Context Protocol) che funge da strato di persistenza e memoria per gli agenti. Gestisce tre risorse distinte montate come volumi:

- **Vector DB** (`/app/data/vector_db`): database ChromaDB con embedding `all-MiniLM-L6-v2` che contiene attacchi storici indicizzati per la ricerca vettoriale (RAG).
- **Sessioni** (`/app/data/sessions`): file JSONL per sessione (creata con ip attaccante + giorno), con la sequenza storica di comandi.
- **Artefatti** (`/app/data/artifacts`): file JSONL con gli artefatti di inganno già generati, indicizzati per comando predetto.

Espone quattro tool MCP:

| Tool | Usato da | Funzione |
|------|----------|----------|
| `log_session_event` | PredictiveAgent | Appende il nuovo comando al file di sessione |
| `get_session_history` | PredictiveAgent | Recupera gli ultimi N comandi della sessione |
| `retrieve` | PredictiveAgent | Query vettoriale su ChromaDB per trovare attacchi simili (RAG) |
| `get_artifact` | ForgerAgent | Cerca se esiste già un artefatto per il comando predetto |
| `save_artifact` | ForgerAgent | Salva un nuovo artefatto nel file JSONL |

---

### 4. MCP Forgery Container

**Directory:** `mcpForgeryContainer/`  
**Immagine base:** Python 3.10 slim  
**Porta:** 8000 (MCP/SSE)  
**Privilegio speciale:** accesso al socket Docker (`/var/run/docker.sock`)

È il "braccio operativo" del sistema. Espone un singolo tool MCP:

**`deploy_artifact(intended_path, content)`**: inietta fisicamente un file nel filesystem del container honeypot senza che l'honeypot debba essere modificato o riavviato. Lo fa costruendo un archivio TAR in memoria RAM e usandolo tramite la Docker API (`put_archive`), equivalente a `docker cp`. Il file appare nell'honeypot come se fosse sempre stato lì.

---

## Flusso di Esecuzione End-to-End

```
Attaccante digita: "cat /etc/passwd"
        │
        ▼
[fakeshell] trigger_ai() → HTTP POST {session_id, cmd, ip, cwd, ...}
        │
        ▼
[HoneypotListener] dispatch(event)
        │
        ├─── FASE 1: PREDIZIONE ─────────────────────────────────────────
        │    [PredictiveAgent]
        │    ├─ Tool: log_session_event   → salva "cat /etc/passwd" nel log
        │    ├─ Tool: get_session_history → recupera ultimi 5 comandi della sessione
        │    ├─ Tool: retrieve            → RAG su ChromaDB (attacchi simili)
        │    └─ LLM genera prediction:  ["ls -la /etc", "cat /etc/shadow", "id", ...]
        │
        └─── FASE 2: FORGERY (parallela, un ForgerAgent per predizione) ──
             [ForgerAgent-0] per "ls -la /etc"
             ├─ Tool: get_artifact("ls -la /etc") → non trovato
             ├─ LLM genera artefatto JSON ({path, content})
             ├─ Tool: save_artifact(...)  → salva nel database JSONL degli artefatti
             └─ Tool: deploy_artifact(intended_path, content)
                  └─ [mcp-forgery] Docker API → TAR in memoria → honeypot filesystem
             
             [ForgerAgent-1] per "cat /etc/shadow"  ← in parallelo
             ...

Quando l'attaccante esegue "ls -la /etc", trova già i file falsi.
```

---

## Architettura Agentica Interna

### AgentConnector

**File:** `agentContainer/agentArchitecture/agent_connector.py`

Astrae la comunicazione con il modello LLM, supportando tre provider in modo trasparente:

- **Google Gemini** (SDK `google-genai`)
- **OpenAI** (SDK `openai`)
- **OpenRouter** (SDK `openai` con base_url alternativo)
- **Locale** (LM Studio via OpenAI-compat, `host.docker.internal:1234`)

Il provider e la chiave vengono letti dal Docker secret. Il metodo principale è `create_agentic_chat()`, che restituisce una sessione di chat configurata con system prompt e tool definitions, wrappata in un oggetto con interfaccia unificata.

Il wrapper unificato (`adapter_connector.py`) nasconde le differenze strutturali tra gli SDK:
- Google non richiede `call_id` nei tool result; OpenAI sì.
- Google usa `FunctionDeclaration`; OpenAI usa JSON Schema.
- Google gestisce la history internamente; OpenAI richiede di passarla esplicitamente.

### PredictiveAgent

**File:** `agentContainer/agentArchitecture/agent_predictive/predictive_core.py`

Agente autonomo che implementa il ciclo RAG + predizione. È un **async context manager**: apre una connessione SSE persistente verso il backend MCP all'avvio e la riusa per ogni richiesta, evitando overhead di reconnessione.

Il metodo `decide(event)` avvia un loop agentico:
1. Invia il comando come messaggio iniziale (isolato in tag `<untrusted_data>` per prevenire prompt injection).
2. L'LLM chiama autonomamente i tool nell'ordine corretto.
3. Il loop si arresta quando l'LLM produce testo puro (predizione finale).

Due guardrail di sicurezza:
- `MAX_ITERATIONS = 4`: previene loop infiniti.
- `REQUIRED_TOOLS`: verifica che tutti e tre i tool obbligatori siano stati chiamati prima di accettare la predizione.

### ForgerAgent

**File:** `agentContainer/agentArchitecture/agent_forger/forger_core.py`

Analogo al PredictiveAgent, ma orientato alla generazione e al deployment di artefatti. Mantiene **due** connessioni SSE persistenti: una verso il backend (per `get_artifact`/`save_artifact`) e una verso mcp-forgery (per `deploy_artifact`).

Il workflow previsto è: controlla knowledge base → genera o recupera artefatto → deploya nel honeypot → produce JSON finale come output.

Il sistema ne istanzia `NUM_PREDICTION` copie in pool, una per ogni predizione, così i deployment avvengono in parallelo.

### HoneypotListener (Orchestratore)

**File:** `agentContainer/agentArchitecture/honeypot_listener.py`

Coordina PredictiveAgent e ForgerAgent tramite il meccanismo `lifespan` di FastAPI. All'avvio, apre tutte le connessioni SSE; allo shutdown le chiude in modo ordinato. 

---

## Struttura del Progetto

```
agenticPredictiveDeception/
│
├── docker-compose.yml              # Orchestrazione dei 4 container
├── .env                            # Chiave API e configurazione LLM (→ Docker secret)
├── .gitignore
│
├── honeypotContainer/
│   ├── Dockerfile                  # OpenSSH + fakeshell come login shell
│   └── fakeshell.py                # Shell SSH simulata + notifica AI
│
├── agentContainer/
│   ├── Dockerfile
│   ├── requirements.txt            # fastapi, uvicorn, google-genai, openai, fastmcp
│   └── agentArchitecture/
│       ├── honeypot_listener.py    # FastAPI app + orchestratore (HoneypotListener)
│       ├── agent_connector.py      # Astrazione multi-provider LLM
│       ├── adapter_connector.py    # Wrapper unificati (Google/OpenAI)
│       ├── agent_predictive/
│       │   ├── predictive_core.py  # PredictiveAgent (RAG + predizione)
│       │   ├── predictive_policies.py  # System prompt del PredictiveAgent
│       │   └── __init__.py
│       └── agent_forger/
│           ├── forger_core.py      # ForgerAgent (generazione + deploy artefatti)
│           ├── forger_policies.py  # System prompt del ForgerAgent
│           └── __init__.py
│
├── backendContainer/
│   ├── Dockerfile                  # Python + ChromaDB + SentenceTransformers
│   ├── requirements.txt
│   └── mcp_server.py               # Server MCP: RAG, sessioni, artefatti
│
└── mcpForgeryContainer/
    ├── Dockerfile
    ├── requirements.txt
    └── mcp_server.py               # Server MCP: deploy artefatti via Docker API
```

---

## Configurazione e Avvio

### Prerequisiti

- Docker e Docker Compose installati
- Un database ChromaDB pre-popolato con attacchi storici (collection `honeypot_attacks`)
- Una chiave API per un provider LLM (OpenRouter, OpenAI o Google)


### Percorsi volumi (docker-compose.yml)

Nel `docker-compose.yml`, aggiorna i percorsi bind mount del container `backend` con i percorsi locali corretti:

```yaml
- source: /percorso/locale/chroma_storage   # ChromaDB vector store
  target: /app/data/vector_db
- source: /percorso/locale/sessions         # Log sessioni per attaccante
  target: /app/data/sessions
- source: /percorso/locale/artifacts        # Artefatti generati (JSONL)
  target: /app/data/artifacts
```

Inoltre puoi modificare altri parametri (del container `agentic-system`) quali:
```yaml
environment:
    - PROVIDER=<cloud/locale>                                       
    - MODEL_NAME=<modello>                                          
    - NUM_PREDICTION=<numero di prediction>                         
```

### File `.env`

Crea o modifica il file `.env` nella root del progetto:

```env
LLM_API_KEY=<la_tua_chiave_api>
LLM_SDK=openrouter       # oppure: google, openai
```

### Avvio

```bash
git clone https://github.com/melomatte/agenticPredictiveDeception.git
cd agenticPredictiveDeception

docker-compose up --build -d
```

L'honeypot sarà raggiungibile su `ssh honeypot@localhost -p 2222` (password: `password123`).
Utile leggere i log degli altri container tramite comando `docker compose logs -f <nome-container>`

---

## Punti Fondamentali di Design

**Proattività vs. reattività.** I sistemi honeypot tradizionali registrano passivamente ciò che un attaccante fa. Questo sistema anticipa il passo successivo e modifica l'ambiente prima che avvenga

**Parallelismo nel forgery.** Vengono istanziati `NUM_PREDICTION` ForgerAgent in pool (uno per predizione), ognuno con le proprie connessioni SSE. I `k` artefatti vengono generati e deployati in parallelo con `asyncio.wait()`.

**Iniezione senza modifica dell'honeypot.** Il MCP Forgery sfrutta il socket Docker (`docker cp` via API) per iniettare file nel container honeypot dall'esterno, senza che la fakeshell debba gestire scritture o essere modificata.

**Anti-prompt injection.** I dati provenienti dall'attaccante (comandi, IP, etc.) vengono sempre isolati in tag `<untrusted_data>` nel messaggio inviato all'LLM, con istruzione esplicita di trattarli come dati grezzi e non come istruzioni.

**Guardrail anti-allucinazione.** Il loop agentico verifica post-esecuzione che tutti i tool obbligatori siano stati effettivamente chiamati. Se manca anche solo uno, la predizione viene scartata e non avvia la fase forgery.

**Astrazione multi-provider.** `AgentConnector` e i wrapper in `adapter_connector.py` consentono di passare da Google Gemini a OpenAI a OpenRouter (o a un modello locale via LM Studio) modificando due righe nel `.env`, senza toccare la logica degli agenti.

---

## Contesto di Ricerca

Il progetto esplora tre aree all'intersezione della cybersecurity moderna:

**Cyber Deception adattiva**: a differenza dei honeypot statici (file di password fissi, configurazioni immutabili), questo sistema genera contenuti ingannevoli contestualmente appropriati per ogni attaccante, basandosi sul suo comportamento specifico.

**Agentic AI applicata alla sicurezza**: gli agenti non eseguono un semplice prompt/risposta ma operano in loop autonomi con tool calling, gestione dello stato della conversazione e coordinamento multi-agente.

**Predictive Threat Modeling con RAG**: la combinazione di memoria di sessione (ultimi N comandi) e recupero vettoriale (attacchi storici simili) permette di contestualizzare la predizione sia nel presente (questa sessione) che nel passato (attacchi analoghi).

---

## Autore

**melomatte** — [Profilo GitHub](https://github.com/melomatte)