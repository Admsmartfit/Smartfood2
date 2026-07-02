#!/bin/bash
# SmartFood Ops 360 — Script de inicialização
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Carrega .env se existir
if [ -f ".env" ]; then
    export $(grep -v '^#' .env | xargs)
fi

PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"

# Cria ambiente virtual se não existir
if [ ! -d "venv" ]; then
    echo "[SmartFood] Criando ambiente virtual Python..."
    python3 -m venv venv
fi

# Ativa o ambiente virtual
source venv/bin/activate

# Instala/atualiza dependências
echo "[SmartFood] Verificando dependências..."
pip install -q -r requirements.txt

# Cria admin padrão se necessário
echo "[SmartFood] Verificando usuário admin..."
python3 seed_admin.py

# Inicia o servidor
echo "[SmartFood] Iniciando em http://${HOST}:${PORT} ..."
exec uvicorn main:app --host "$HOST" --port "$PORT" --workers 1
