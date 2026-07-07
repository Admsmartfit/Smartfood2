#!/bin/bash
# SmartFood Ops 360 — Instalador para Linux (Ubuntu/Debian/Raspberry Pi OS)
# Execute como root: sudo bash install_linux.sh

set -e

INSTALL_DIR="/opt/smartfood"
APP_USER="smartfood"

echo "======================================================"
echo "  SmartFood Ops 360 — Instalador Linux"
echo "======================================================"

# ── 1. Verifica root ───────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    echo "ERRO: Execute com sudo: sudo bash install_linux.sh"
    exit 1
fi

# ── 2. Instala dependências do sistema ─────────────────────
echo ""
echo "[1/6] Instalando Python e dependências do sistema..."
apt-get update -qq
apt-get install -y python3 python3-venv python3-pip git curl

# ── 3. Cria usuário e diretório ────────────────────────────
echo ""
echo "[2/6] Criando usuário '${APP_USER}'..."
if ! id "$APP_USER" &>/dev/null; then
    useradd -r -s /bin/bash -d "$INSTALL_DIR" "$APP_USER"
    echo "     Usuário '${APP_USER}' criado."
else
    echo "     Usuário '${APP_USER}' já existe."
fi
usermod -aG lp "$APP_USER" || true

# ── 4. Copia arquivos do projeto ───────────────────────────
echo ""
echo "[3/6] Copiando arquivos do projeto para ${INSTALL_DIR} ..."
mkdir -p "$INSTALL_DIR"

# Copia tudo EXCETO venv, caches e o banco de dados sqlite para não sobrescrever dados de produção
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
rsync -a --exclude='venv/' --exclude='__pycache__/' --exclude='*.pyc' --exclude='smartfood.db' \
    "${SOURCE_DIR}/" "${INSTALL_DIR}/"

chown -R "${APP_USER}:${APP_USER}" "$INSTALL_DIR"

# ── 5. Cria ambiente virtual e instala pacotes ─────────────
echo ""
echo "[4/6] Criando ambiente virtual Python..."

# Remove venv antigo/corrompido se existir
rm -rf "${INSTALL_DIR}/venv"

# Cria venv com caminho absoluto
sudo -u "$APP_USER" python3 -m venv "${INSTALL_DIR}/venv"

# Usa caminhos absolutos para evitar problemas de permissão
VENV_PIP="${INSTALL_DIR}/venv/bin/pip"
VENV_PY="${INSTALL_DIR}/venv/bin/python3"

# Muda para o diretório de instalação para executar os comandos com o contexto correto
cd "${INSTALL_DIR}"

sudo -u "$APP_USER" "$VENV_PIP" install -q --upgrade pip
sudo -u "$APP_USER" "$VENV_PIP" install -q -r "${INSTALL_DIR}/requirements.txt"

echo "     Inicializando banco de dados..."
sudo -u "$APP_USER" "$VENV_PY" "${INSTALL_DIR}/seed_admin.py"

# ── 6. Configura systemd ───────────────────────────────────
echo ""
echo "[5/6] Configurando serviço systemd..."

# Gera o arquivo de serviço com caminhos absolutos já preenchidos
SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")

cat > /etc/systemd/system/smartfood.service << EOF
[Unit]
Description=SmartFood Ops 360
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=smartfood
Environment="SECRET_KEY=${SECRET}"
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable smartfood
systemctl restart smartfood

# ── 7. Mostra status ───────────────────────────────────────
echo ""
echo "[6/6] Verificando status do serviço..."
sleep 2
systemctl status smartfood --no-pager || true

LOCAL_IP=$(hostname -I | awk '{print $1}')

echo ""
echo "======================================================"
echo "  INSTALACAO CONCLUIDA!"
echo "======================================================"
echo ""
echo "  Acesse em qualquer dispositivo da rede local:"
echo "  --> http://${LOCAL_IP}:8000"
echo ""
echo "  Login padrao:"
echo "  Email : admin@smartfood.com"
echo "  Senha : smartfood2026"
echo ""
echo "  IMPORTANTE: Troque a senha do admin apos o primeiro login!"
echo ""
echo "  Comandos uteis:"
echo "  Ver logs    : sudo journalctl -u smartfood -f"
echo "  Reiniciar   : sudo systemctl restart smartfood"
echo "  Parar       : sudo systemctl stop smartfood"
echo "  Status      : sudo systemctl status smartfood"
echo "======================================================"
