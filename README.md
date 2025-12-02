# UFRO Orquestador MCP

Agente orquestador que integra verificación de identidad (PP2) y consultas de normativa UFRO (PP1) con analítica en MongoDB.

## Características

- **Identificación de Personas**: Integración paralela con múltiples servicios PP2
- **Consultas de Normativa**: Integración con chatbot RAG UFRO (PP1)
- **Analítica Avanzada**: 6 endpoints de métricas operativas en MongoDB
- **API REST Completa**: 12 endpoints incluyendo salud y métricas
- **MCP Server**: 5 tools para LLMs
- **Workflow N8N**: Implementación alternativa completa

## Requisitos

- Python 3.11+
- Docker & Docker Compose
- MongoDB (incluido en docker-compose)
- URLs válidas de servicios PP1 y PP2

## Instalación

### 1. Clonar y configurar entorno

```bash
git clone <repository>
cd orquestador-MCP
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configurar variables de entorno

```bash
cp .env.example .env
```

Editar `.env` con las URLs reales de tus servicios:

```bash
# MongoDB
MONGO_URI=mongodb://admin:password123@localhost:27017/ufro_master?authSource=admin
DB_NAME=ufro_master

# PP1 Integration (ACTUALIZAR CON TU URL)
PP1_URL=https://tu-pp1-url.com/ask
PP1_TIMEOUT=10.0

# PP2 Integration
PP2_TIMEOUT=5.0
THRESHOLD=0.75
MARGIN=0.2

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
MAX_IMAGE_SIZE_MB=5
ALLOWED_IMAGE_TYPES=image/jpeg,image/png

# Security
API_SECRET_KEY=your-secret-key-change-this
TOKEN_EXPIRE_HOURS=24

# MCP Server
MCP_SERVER_PORT=8001
```

### 3. Configurar servicios PP2

Editar `conf/registry.yaml` con tus servicios:

```yaml
pp2_services:
  - name: "Tu Nombre"
     endpoint_verify: "http://54.205.31.20:5000/verify"
    threshold: 0.75
    active: true
```

### 4. Iniciar MongoDB

```bash
docker-compose up -d
```

Verificar que esté corriendo:
```bash
docker-compose ps
```

### 5. Crear índices en MongoDB

```bash
export PYTHONPATH=$(pwd)
export $(cat .env | grep -v '^#' | xargs)
python db/ensure_indexes.py
```

### 6. Iniciar la aplicación

```bash
python api/app.py
```

El servidor iniciará en `http://localhost:8000`

## Uso

### Endpoint Principal

**POST /identify-and-answer**

```bash
curl -X POST "http://localhost:8000/identify-and-answer" \
  -H "X-User-Id: test-user" \
  -H "X-User-Type: student" \
  -F "image=@foto.jpg" \
  -F "question=¿Puedo retractarme de una asignatura?"
```

### Verificar Salud del Sistema

```bash
curl http://localhost:8000/healthz
```

### Métricas del Sistema

```bash
# Resumen general
curl "http://localhost:8000/metrics/summary?days=7"

# Por tipo de usuario
curl "http://localhost:8000/metrics/by-user-type?days=7"

# Distribución de decisiones
curl "http://localhost:8000/metrics/decisions?days=7"

# Performance de servicios
curl "http://localhost:8000/metrics/services?days=7"

# Volumen por hora
curl "http://localhost:8000/metrics/volume?days=7"

# Timeouts de PP2
curl "http://localhost:8000/metrics/pp2-timeouts?days=7"
```

## MCP Server (Opcional)

Para usar las herramientas MCP con LLMs:

```bash
# Terminal separado
source venv/bin/activate
export PYTHONPATH=$(pwd)
python mcp_server/server.py
```

## Estructura del Proyecto

```
orquestador-MCP/
├── api/
│   └── app.py                 # FastAPI principal con 12 endpoints
├── orchestrator/
│   ├── pp2_client.py          # Cliente PP2 concurrente
│   ├── pp1_client.py          # Cliente PP1 RAG
│   ├── fuse.py                # Lógica de fusión
│   └── schemas.py             # Modelos Pydantic
├── db/
│   ├── mongo.py               # Conexión MongoDB
│   ├── ensure_indexes.py      # Índices optimizados
│   └── queries.py             # Queries de métricas
├── mcp_server/
│   ├── server.py              # MCP Server con 5 tools
│   └── manifest.json          # Configuración MCP
├── n8n/
│   └── pp3_workflow.json      # Workflow N8N alternativo
├── conf/registry.yaml         # Configuración servicios PP2
├── scripts/
│   ├── test_mongo.py          # Tests de conexión
│   ├── run_gunicorn.sh        # Script de producción
│   └── load_test.sh           # Tests de carga
├── tests/
│   ├── test_api.py            # Tests de API
│   └── test_fuse.py           # Tests de lógica
├── docker-compose.yml         # MongoDB + Mongo Express
├── requirements.txt           # Dependencias
├── .env.example               # Template de configuración
└── README.md                  # Esta documentación
```

## Arquitectura

```
┌─────────────┐    ┌──────────────┐    ┌─────────────────┐
│   Cliente   │───▶│  API REST    │───▶│  Orquestador    │
│             │    │ (12 endpoints)│    │                │
└─────────────┘    └──────────────┘    └─────────┬───────┘
                            │                     │
                   ┌────────▼────────┐           ▼
                   │   MCP Server    │    ┌─────────────┐
                   │  (5 tools LLM)  │    │MongoDB      │
                   └─────────────────┘    │ Analytics   │
                                          └─────────────┘
                   ┌─────────────────┐           ▲
                   │  N8N Workflow   │           │
                   │ (Alternative)   │───────────┘
                   └─────────────────┘

     PP2 Services (Paralelo)          PP1 Service
    ┌────────────────────┐           ┌──────────────┐
    │ PP2₁ (Tu Nombre)   │◄──────────┤              │
    │ PP2₂ (Otro servicio)│           │   PP1 RAG    │
    │ ...                │           │   UFRO       │
    │ PP2ₙ               │           │              │
    └────────────────────┘           └──────────────┘
```

## Lógica de Fusión

El sistema utiliza parámetros configurables:
- **Threshold (τ=0.75)**: Puntaje mínimo para considerar identificación válida
- **Margin (δ=0.2)**: Margen mínimo entre primer y segundo candidato

### Decisiones:
- **IDENTIFIED**: Score ≥ τ (0.75) Y margen ≥ δ (0.2) respecto al segundo
- **AMBIGUOUS**: Múltiples candidatos > τ con margen < δ
- **UNKNOWN**: Ningún candidato alcanza τ

## Producción

### Con Gunicorn

```bash
chmod +x scripts/run_gunicorn.sh
./scripts/run_gunicorn.sh
```

O manualmente:
```bash
gunicorn api.app:app -w 4 -b 0.0.0.0:8000 --timeout 30
```

### Mongo Express (Interfaz Web)

Acceder a `http://localhost:8081`
- Usuario: `admin`
- Password: `pass`

### Tests de Carga

```bash
chmod +x scripts/load_test.sh
./scripts/load_test.sh
```

## Comandos Útiles

### Desarrollo

```bash
# Iniciar stack completo
docker-compose up -d
source venv/bin/activate
export PYTHONPATH=$(pwd)
export $(cat .env | grep -v '^#' | xargs)
python api/app.py
```

### Testing

```bash
# Test MongoDB
python scripts/test_mongo.py

# Test API health
curl http://localhost:8000/healthz

# Tests unitarios
python tests/test_api.py
```

### Monitoreo

```bash
# Logs MongoDB
docker-compose logs mongodb

# Logs Mongo Express
docker-compose logs mongo-express
```

## Respuesta de Ejemplo

```json
{
  "decision": "identified",
  "identity": {"name": "Ana Pérez", "score": 0.88},
  "candidates": [
    {"name": "Ana Pérez", "score": 0.88},
    {"name": "Luis Soto", "score": 0.41}
  ],
  "normativa_answer": {
    "text": "Puedes retractarte dentro de 10 días corridos...",
    "citations": [
      {"doc": "Reglamento Académico", "page": "12", "url": "https://..."}
    ]
  },
  "timing_ms": 154.2,
  "request_id": "4b9d2c..."
}
```

## Métricas Implementadas

1. **Summary**: Requests totales, tiempo promedio, tasa de éxito
2. **By User Type**: Breakdown por estudiante/profesor/externo
3. **Decisions**: Distribución identified/ambiguous/unknown
4. **Services**: Performance PP1/PP2, timeouts, latencias
5. **Volume**: Volumen por hora para análisis temporal
6. **PP2 Timeouts**: Ranking de servicios por confiabilidad
