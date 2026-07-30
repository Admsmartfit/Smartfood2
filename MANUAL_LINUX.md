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
http://192.168.15.XX:8000
```
(o `XX` depende da sua rede — veja a seção 9 para o endereço real em uso hoje)

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

Hoje o servidor recebe IP por **DHCP** (rede `192.168.15.0/24`, gateway `192.168.15.1`,
interface `enp2s0` — confirme com `ip route | grep default` e `hostname -I`, já que
isso muda conforme o roteador/rede do local). Sem IP fixo, o endereço pode trocar a
cada reboot do roteador. Para fixar:

### Ubuntu/Debian com Netplan

```bash
# Descobre a interface de rede (no servidor atual: enp2s0)
ip link show

# Edita a configuração
sudo nano /etc/netplan/01-netcfg.yaml
```

Substitua o conteúdo por (ajuste a interface e o IP escolhido conforme sua rede real):

```yaml
network:
  version: 2
  ethernets:
    enp2s0:         # troque pelo nome da sua interface (veja "ip link show")
      dhcp4: no
      addresses:
        - 192.168.15.50/24    # IP fixo desejado — dentro da MESMA sub-rede do
                               # roteador, fora da faixa que o DHCP distribui
      gateway4: 192.168.15.1  # IP do seu roteador (veja "ip route | grep default")
      nameservers:
        addresses: [8.8.8.8, 8.8.4.4]
```

⚠️ **Use a sub-rede real da sua rede**, não copie os números acima sem conferir —
um IP fixo em `192.168.1.x` numa rede que na verdade é `192.168.15.x` (ou qualquer
outra) fica inacessível: os pacotes não chegam a lugar nenhum (`ERR_CONNECTION_TIMED_OUT`
no navegador, silêncio total no ping), mesmo com o serviço rodando perfeitamente.
Descubra a sub-rede certa com `ip route | grep default` no servidor, e confira que o
computador que vai acessar está na mesma faixa (`ipconfig` no Windows).

Aplica:
```bash
sudo netplan apply
```

Após isso o SmartFood estará **sempre no IP escolhido** (ex.: `http://192.168.15.50:8000`).

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

Quando receber uma versão nova do projeto (ex.: copiada para `~/Smartfood2`):

```bash
# Para o serviço
sudo systemctl stop smartfood

# Copia os arquivos novos, SEM sobrescrever o banco de dados nem o venv de produção
sudo rsync -a --exclude 'smartfood.db' --exclude 'venv' ~/Smartfood2/ /opt/smartfood/

# Garante que tudo continua pertencendo ao usuário smartfood
sudo chown -R smartfood:smartfood /opt/smartfood

# Atualiza dependências no venv de produção
cd /opt/smartfood
sudo -u smartfood venv/bin/pip install -r requirements.txt

# Reinicia
sudo systemctl start smartfood
sudo systemctl status smartfood   # aperte "q" para sair do status
```

⚠️ **Dois erros comuns nesse passo:**

- **`--exclude 'venv'` é obrigatório.** O ambiente virtual de produção (`/opt/smartfood/venv`)
  tem pacotes compilados específicos daquele ambiente — copiar um `venv/` de outra pasta por
  cima quebra a instalação. Deixe o `pip install -r requirements.txt` do passo seguinte
  atualizar os pacotes *dentro* do venv existente.
- **Nunca rode `sudo -u smartfood venv/bin/pip ...` a partir da sua home (`~/Smartfood2`).**
  Diretórios de home (`/home/SEU_USUARIO`) normalmente são `750` — só o dono acessa. O usuário
  `smartfood` não consegue nem entrar ali, e qualquer comando dá `Permission denied` mesmo com
  o arquivo tendo permissão de execução. Sempre rode o `pip install` de dentro de
  `/opt/smartfood` (`cd /opt/smartfood` antes), como no exemplo acima.

Se o `requirements.txt` ganhou uma dependência nova (aconteceu com `pillow`, usada para
gerar QR Code e texto em bitmap na impressão de etiquetas), o `pip install -r
requirements.txt` acima já resolve — não precisa de nenhum passo extra.

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

Com o servidor rodando, qualquer dispositivo na **mesma sub-rede** pode acessar. Endereço
atual do servidor (DHCP, pode mudar — veja seção 4 para fixar):

| Dispositivo | Endereço no navegador |
|-------------|----------------------|
| Computador / notebook | `http://192.168.15.8:8000` |
| Celular | `http://192.168.15.8:8000` |
| Tablet (produção, QR) | `http://192.168.15.8:8000` |

**Funcionários com perfil CLIENTE** acessam direto em:
```
http://192.168.15.8:8000/loja
```
(serão redirecionados automaticamente para o portal deles)

Se o endereço parar de responder de um dia para o outro, confira primeiro se o IP do
servidor mudou (`hostname -I` nele) antes de suspeitar do serviço — é o sintoma mais comum
quando o IP vem de DHCP e não foi fixado (seção 4).

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

Primeiro descarte o motivo mais comum — **sub-rede errada**, não firewall. Sintoma típico:
o navegador trava em "carregando" e no final dá `ERR_CONNECTION_TIMED_OUT` (diferente de
"conexão recusada" — timeout significa que o pacote nem chegou a um destino que responde).

```bash
# No servidor: confirma o IP e a sub-rede atuais
hostname -I
ip route | grep default

# No computador que está tentando acessar (Windows, PowerShell):
# Get-NetIPAddress -AddressFamily IPv4
```

Se o servidor está em `192.168.15.x` e o computador em `192.168.1.x` (ou qualquer sub-rede
diferente), eles simplesmente não se enxergam — não é bug do SmartFood nem do firewall.
Corrija o IP usado no navegador (ou a configuração de rede) para a mesma faixa.

Só depois de confirmar que ambos estão na mesma sub-rede, verifique o firewall:

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
