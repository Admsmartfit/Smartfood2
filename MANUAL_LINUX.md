# SmartFood Ops 360 — Manual Linux (Rede Local)

## Pré-requisitos

| Item | Requisito mínimo |
|------|-----------------|
| Sistema operacional | Ubuntu 20.04+ / Debian 11+ / Raspberry Pi OS (64-bit) |
| Python | 3.10 ou superior |
| RAM | 512 MB livres |
| Disco | 500 MB livres |
| Rede | IP fixo recomendado (veja abaixo) |

---

## 1. Transferir o projeto para o Linux

### Opção A — Via pen drive / rede local

Copie a pasta `Smartfood2` para o Linux. Exemplo:

```bash
# No Linux, com o pen drive montado em /media/usb:
cp -r /media/usb/Smartfood2 ~/smartfood
```

### Opção B — Via Git (se tiver repositório)

```bash
git clone <URL_DO_REPOSITORIO> ~/smartfood
cd ~/smartfood
```

---

## 2. Instalação automática (recomendado)

Execute **uma única vez** como administrador:

```bash
cd ~/smartfood
sudo bash install_linux.sh
```

O script vai:
- Instalar Python e dependências do sistema
- Criar usuário `smartfood` dedicado
- Copiar os arquivos para `/opt/smartfood`
- Criar o ambiente virtual Python
- Inicializar o banco de dados e criar o admin
- Registrar e iniciar o serviço automático no systemd

Ao final, o script mostra o endereço de acesso:
```
http://192.168.1.XX:8000
```

---

## 3. Instalação manual (alternativa)

Se preferir controle total, execute passo a passo:

```bash
# Instala dependências do sistema
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip

# Acessa o diretório do projeto
cd ~/smartfood

# Cria ambiente virtual
python3 -m venv venv
source venv/bin/activate

# Instala pacotes Python
pip install -r requirements.txt

# Inicializa banco e cria admin
python3 seed_admin.py

# Inicia o servidor (teste manual)
uvicorn main:app --host 0.0.0.0 --port 8000
```

Acesse em: `http://IP_DA_MAQUINA:8000`

Para descobrir o IP:
```bash
hostname -I
```

---

## 4. Configurar IP fixo (recomendado para rede local)

Para que o endereço nunca mude, configure IP fixo na máquina Linux.

### Ubuntu/Debian com Netplan

```bash
# Descobre a interface de rede
ip link show

# Edita a configuração
sudo nano /etc/netplan/01-netcfg.yaml
```

Substitua o conteúdo por:

```yaml
network:
  version: 2
  ethernets:
    eth0:           # troque pelo nome da sua interface
      dhcp4: no
      addresses:
        - 192.168.1.100/24   # IP fixo desejado
      gateway4: 192.168.1.1  # IP do seu roteador
      nameservers:
        addresses: [8.8.8.8, 8.8.4.4]
```

Aplica:
```bash
sudo netplan apply
```

Após isso o SmartFood estará **sempre em `http://192.168.1.100:8000`**.

---

## 5. Iniciar automaticamente com o Linux

O instalador automático já configura isso. Para verificar:

```bash
# Verifica se o serviço está ativo e configurado para iniciar no boot
sudo systemctl status smartfood
sudo systemctl is-enabled smartfood   # deve mostrar "enabled"
```

### Para configurar manualmente (se não usou o instalador)

```bash
# Copia o arquivo de serviço
sudo cp /opt/smartfood/smartfood.service /etc/systemd/system/

# Edita o arquivo para ajustar caminhos e usuário
sudo nano /etc/systemd/system/smartfood.service

# Ativa e inicia
sudo systemctl daemon-reload
sudo systemctl enable smartfood
sudo systemctl start smartfood
```

---

## 6. Comandos do dia a dia

```bash
# Ver se está rodando
sudo systemctl status smartfood

# Ver logs em tempo real
sudo journalctl -u smartfood -f

# Ver últimas 50 linhas de log
sudo journalctl -u smartfood -n 50

# Reiniciar (após atualizar o código)
sudo systemctl restart smartfood

# Parar
sudo systemctl stop smartfood

# Iniciar
sudo systemctl start smartfood

# Desativar (não inicia mais no boot)
sudo systemctl disable smartfood
```

---

## 7. Atualizar o sistema

Quando receber uma versão nova do projeto:

```bash
# Para o serviço
sudo systemctl stop smartfood

# Copia os arquivos novos (preserve o banco de dados!)
sudo cp -r ~/smartfood_novo/* /opt/smartfood/
# NÃO sobrescreva o arquivo smartfood.db se não quiser perder os dados
sudo chown -R smartfood:smartfood /opt/smartfood

# Atualiza dependências
cd /opt/smartfood
sudo -u smartfood venv/bin/pip install -r requirements.txt

# Reinicia
sudo systemctl start smartfood
```

---

## 8. Backup do banco de dados

O banco é um único arquivo SQLite:

```bash
# Copia o banco para um local seguro
cp /opt/smartfood/smartfood.db ~/backup_smartfood_$(date +%Y%m%d).db
```

Para automatizar backup diário:

```bash
# Edita o crontab do usuário
crontab -e
```

Adiciona a linha:
```
0 3 * * * cp /opt/smartfood/smartfood.db /home/SEU_USUARIO/backups/smartfood_$(date +\%Y\%m\%d).db
```

---

## 9. Acessar de outros dispositivos

Com o servidor rodando, qualquer dispositivo na mesma rede local pode acessar:

| Dispositivo | Endereço no navegador |
|-------------|----------------------|
| Computador / notebook | `http://192.168.1.100:8000` |
| Celular | `http://192.168.1.100:8000` |
| Tablet (produção, QR) | `http://192.168.1.100:8000` |

**Funcionários com perfil CLIENTE** acessam direto em:
```
http://192.168.1.100:8000/loja
```
(serão redirecionados automaticamente para o portal deles)

---

## 10. Primeiro acesso

| Campo | Valor |
|-------|-------|
| Endereço | `http://IP_DA_MAQUINA:8000` |
| Email | `admin@smartfood.com` |
| Senha | `smartfood2026` |

**Após o primeiro login:**
1. Vá em **Administração → Usuários**
2. Crie usuários para cada perfil (ADMIN, PRODUCAO, CLIENTE)
3. Crie clientes em **Clientes** e vincule aos usuários CLIENTE
4. Configure os produtos visíveis na loja em **Catálogo Loja**

---

## 11. Solução de problemas

### O serviço não inicia

```bash
# Ver o erro exato
sudo journalctl -u smartfood -n 30 --no-pager
```

### Porta 8000 em uso

```bash
# Verifica o que está usando a porta
sudo ss -tlnp | grep 8000

# Ou muda a porta no arquivo de serviço
sudo nano /etc/systemd/system/smartfood.service
# Altere --port 8000 para --port 8080
sudo systemctl daemon-reload
sudo systemctl restart smartfood
```

### Não consigo acessar de outro dispositivo

```bash
# Verifica se o firewall está bloqueando
sudo ufw status
# Se necessário, libera a porta
sudo ufw allow 8000/tcp
sudo ufw reload
```

### Banco de dados corrompido

```bash
sudo systemctl stop smartfood
# Restaura backup
cp ~/backup_smartfood_DATA.db /opt/smartfood/smartfood.db
sudo chown smartfood:smartfood /opt/smartfood/smartfood.db
sudo systemctl start smartfood
```

---

## Portas padrão

| Porta | Uso |
|-------|-----|
| **8000** | SmartFood Ops 360 (HTTP) |

Sem HTTPS, sem domínio — acesso direto por IP na rede local. Simples e rápido.
