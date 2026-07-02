#!/bin/bash
# SmartFood Ops 360 — Instalador para Linux (Ubuntu/Debian/Raspberry Pi OS)
# Execute como root: sudo bash install_linux.sh

set -e

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
echo "[2/6] Criando usuário 'smartfood'..."
if ! id "smartfood" &>/dev/null; then
    useradd -r -s /bin/bash -d /opt/smartfood smartfood
    echo "     Usuário 'smartfood' criado."
else
    echo "     Usuário 'smartfood' já existe."
fi

# ── 4. Copia arquivos do projeto ───────────────────────────
echo ""
echo "[3/6] Copiando arquivos do projeto para /opt/smartfood ..."
mkdir -p /opt/smartfood
# Se estiver rodando do diretório do projeto, copia tudo para /opt/smartfood
cp -r ./* /opt/smartfood/ 2>/dev/null || true
chown -R smartfood:smartfood /opt/smartfood

# ── 5. Cria ambiente virtual e instala pacotes ─────────────
echo ""
echo "[4/6] Criando ambiente virtual Python..."
cd /opt/smartfood
sudo -u smartfood python3 -m venv venv
sudo -u smartfood venv/bin/pip install -q --upgrade pip
sudo -u smartfood venv/bin/pip install -r requirements.txt

# Cria banco e usuário admin
echo "     Inicializando banco de dados..."
sudo -u smartfood venv/bin/python3 seed_admin.py

# ── 6. Configura systemd ───────────────────────────────────
echo ""
echo "[5/6] Configurando serviço systemd..."
cp smartfood.service /etc/systemd/system/smartfood.service

# Gera chave secreta aleatória
SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
sed -i "s|MUDE-ESTA-CHAVE-SECRETA-ANTES-DE-USAR|$SECRET|g" /etc/systemd/system/smartfood.service

systemctl daemon-reload
systemctl enable smartfood
systemctl restart smartfood

# ── 7. Mostra status ───────────────────────────────────────
echo ""
echo "[6/6] Verificando status do serviço..."
sleep 2
systemctl status smartfood --no-pager || true

# ── Descobre IP local ──────────────────────────────────────
LOCAL_IP=$(hostname -I | awk '{print $1}')

echo ""
echo "======================================================"
echo "  INSTALACAO CONCLUIDA!"
echo "======================================================"
echo ""
echo "  Acesse em qualquer dispositivo da rede local:"
echo "  --> http://${LOCAL_IP}:8000"
echo ""
echo "  Login padrão:"
echo "  Email : admin@smartfood.com"
echo "  Senha : smartfood2026"
echo ""
echo "  IMPORTANTE: Troque a senha do admin após o primeiro login!"
echo ""
echo "  Comandos úteis:"
echo "  Ver logs    : sudo journalctl -u smartfood -f"
echo "  Reiniciar   : sudo systemctl restart smartfood"
echo "  Parar       : sudo systemctl stop smartfood"
echo "  Status      : sudo systemctl status smartfood"
echo "======================================================"
