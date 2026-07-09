# VMN Pulse no Raspberry Pi 4 (appliance com boot por SSD USB)

Guia para rodar o VMN Pulse num Raspberry Pi 4 como appliance dedicado de
monitoramento. O Pi dá conta tranquilo dos ~100 equipamentos: o gargalo nunca
é CPU/RAM, e sim o armazenamento — por isso **este guia assume boot e banco
num SSD USB, não em cartão microSD**.

> Resumo da decisão: o Postgres escreve o tempo todo (~144 mil linhas/dia de
> ping). Cartão microSD é lento para essa carga e tem ciclos de escrita
> limitados — corrompe e morre, geralmente no pior momento. Um monitor que
> morre sozinho é pior que não ter monitor. SSD USB resolve performance e
> durabilidade de uma vez.

---

## 1. Hardware recomendado

- **Raspberry Pi 4 de 4 GB** (8 GB se quiser folga total). Evite o de 2 GB.
- **SSD USB** (120 GB já sobra) para sistema + banco. Não use SD para o banco.
- **Fonte oficial de 3A / 15W.** Subalimentação causa travamentos aleatórios
  que parecem "bug" de software mas são elétricos.
- **Ethernet cabeado, nunca Wi-Fi.** O appliance monitora estabilidade de
  rede; não faz sentido depender de Wi-Fi. Além disso, o teste de internet
  precisa da rota cabeada real.
- Dissipador/ventoinha é bom ter (o Pi esquenta sob carga contínua).

### Atenção ao adaptador USB-SATA / gaveta do SSD

Alguns chipsets antigos (o famigerado **JMicron JMS578**) têm bug de UAS no Pi
e causam corrupção de dados — ironicamente o mesmo problema que estamos
fugindo do SD. Prefira adaptadores com chip **ASMedia** (ex.: ASM1153E),
que são os mais estáveis no Pi. Verifique o chipset antes de comprar.

Se depois de instalar houver travamentos ou erros de I/O, desative o UAS
forçando o modo `usb-storage` (ver seção Troubleshooting no fim).

---

## 2. Atualizar o bootloader para habilitar boot USB

O Pi 4 faz boot direto do USB, mas dependendo da data do firmware pode ser
preciso atualizar o bootloader EEPROM primeiro (tarefa de 2 minutos, feita
uma única vez).

Grave um Raspberry Pi OS Lite num SD **temporário** só para esta etapa, ou use
o **Raspberry Pi Imager** → Misc utility images → "Bootloader" → "USB Boot".

Se preferir pela linha de comando, com o Pi ligado pelo SD temporário:

```bash
sudo apt update && sudo apt full-upgrade -y
sudo rpi-eeprom-update -a
sudo reboot
```

Depois de reiniciar, confirme a ordem de boot (o valor `BOOT_ORDER` deve
priorizar USB — `0xf41` significa "tenta SD, depois USB"; `0xf14` tenta USB
primeiro):

```bash
rpi-eeprom-config
```

Para forçar USB primeiro:

```bash
sudo -E rpi-eeprom-config --edit
# ajuste a linha para: BOOT_ORDER=0xf14
# salve e: sudo reboot
```

Feito isso, desligue, remova o SD e passe a bootar só pelo SSD.

---

## 3. Gravar o sistema no SSD

No seu PC, com o **Raspberry Pi Imager**:

1. Escolha **Ubuntu Server 24.04 LTS (64-bit)** ou **Raspberry Pi OS Lite (64-bit)**.
   Ambos servem; o guia usa comandos compatíveis com os dois.
2. Grave direto no **SSD USB** (não no SD).
3. Nas opções avançadas do Imager (engrenagem), já configure: hostname
   (ex.: `vmn-pulse`), usuário/senha, e **habilite SSH** — assim você acessa
   remoto sem monitor/teclado.

Plugue o SSD no Pi (de preferência numa porta **USB 3.0**, as azuis) e ligue.

---

## 4. Instalar o Docker

Arquitetura ARM64 não é problema: as imagens que usamos (Python, Postgres)
têm build ARM64 oficial. Instale o Docker pelo script oficial:

```bash
sudo apt update && sudo apt upgrade -y
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
# saia e entre de novo na sessão (ou reboot) para o grupo valer
```

Confirme:

```bash
docker --version
docker compose version
```

---

## 5. Baixar e configurar a aplicação

```bash
git clone https://github.com/velaskfr/vmn-pulse-v2.git
cd vmn-pulse-v2
cp .env.example .env
nano .env
```

No `.env`, ajuste no mínimo:

- `POSTGRES_PASSWORD` — senha forte do banco
- `SECRET_KEY` — string aleatória longa. Gere com:
  `openssl rand -hex 32`
- `ADMIN_USER` / `ADMIN_PASSWORD` — login inicial da aplicação
- `DISCORD_WEBHOOK_URL` — webhook do canal de alertas (opcional)
- Limites do speedtest conforme o plano do cliente
  (`SPEEDTEST_MIN_DOWNLOAD_MBPS`, etc.)

> Observação sobre o speedtest no Pi 4: a Ethernet Gigabit real mede links
> até ~940 Mbps de boa. Em links **acima de 1 Gbps**, o próprio Pi vira o
> gargalo e o número sai menor que o real — não é a internet, é o hardware.
> Para ping e links até 1 Gbps, zero problema.

---

## 6. Subir a aplicação

```bash
docker compose up -d --build
```

O `--build` na primeira vez compila a imagem para ARM64 (leva alguns minutos
no Pi, é normal). Acompanhe os logs:

```bash
docker compose logs -f app
```

Esperado: `Usuário admin criado`, `Scheduler de ping iniciado` e, ~20s depois,
o primeiro `Speedtest: ok`.

Acesse de outro computador na rede: `http://IP-DO-PI:8000`

---

## 7. Iniciar no boot automaticamente

O `restart: unless-stopped` no `docker-compose.yml` já faz os containers
subirem sozinhos quando o Docker inicia, e o serviço do Docker já vem
habilitado no boot. Para garantir:

```bash
sudo systemctl enable docker
```

Assim, se faltar energia, o Pi religa e a aplicação volta sozinha.

---

## 8. Posição na rede (o requisito que mais importa)

Recursos de hardware são o de menos. O que define a qualidade do
monitoramento é o Pi **alcançar todos os equipamentos por ICMP (ping)**:

- Se os equipamentos estão em **VLANs segmentadas**, o Pi precisa de rota e o
  firewall precisa **permitir ICMP** entre a VLAN dele e as demais.
- O ideal é colocá-lo numa **VLAN de gerência/management** que já enxergue os
  outros segmentos, ou numa porta com acesso roteado ao restante da rede.
- Para o teste de internet refletir a experiência real, o Pi deve sair pela
  **mesma rota** que os equipamentos usam para a internet.

Complemento útil: cadastre `8.8.8.8` ou `1.1.1.1` como equipamento com
localização "WAN". O ping por minuto mede latência/perda do link
continuamente, sem consumir banda — enquanto o speedtest mede a velocidade.

---

## 9. Manutenção

Atualizar a aplicação quando houver mudanças no repositório:

```bash
cd vmn-pulse-v2
git pull
docker compose up -d --build
```

Ver uso de disco do banco:

```bash
docker exec -it netmonitor-db psql -U netmonitor -d netmonitor \
  -c "SELECT pg_size_pretty(pg_database_size('netmonitor'));"
```

A retenção automática (`RETENTION_DETAIL_DAYS`, padrão 30) compacta os dados
antigos em agregados por hora, então o banco estabiliza em poucos GB.

Backup rápido do banco:

```bash
docker exec -t netmonitor-db pg_dump -U netmonitor netmonitor > backup-$(date +%F).sql
```

---

## Troubleshooting

**Travamentos ou erros de I/O no SSD (bug de UAS):** force o modo
`usb-storage` desabilitando UAS para o seu adaptador. Descubra o ID do
dispositivo com `lsusb` (formato `1234:5678`) e edite o cmdline:

- Raspberry Pi OS: `/boot/firmware/cmdline.txt`
- Ubuntu: `/boot/firmware/cmdline.txt`

Adicione no início da linha (tudo numa linha só), trocando pelos seus IDs:

```
usb-storage.quirks=1234:5678:u
```

Reinicie. Isso costuma resolver corrupção causada por adaptadores problemáticos.

**Speedtest sempre falhando:** confirme saída para a internet e que o
container tem DNS. Um `docker compose restart app` após configurar a rede
costuma resolver.

**Não bota mais pelo USB:** revise o `BOOT_ORDER` na EEPROM (seção 2) e teste
o SSD noutra porta USB 3.0 (as azuis).

---

## Por que o Pi 4 é uma boa base de appliance

Baixo consumo (~5W), silencioso, barato e replicável. Com o sistema todo no
SSD, vira um pacote fechado que você pré-configura, leva ao cliente, pluga na
porta de gerência e entrega funcionando. Para mais fôlego e boot NVMe nativo
(via HAT M.2), o **Pi 5** é o próximo passo — elimina de vez a questão do
armazenamento e eleva o teto do speedtest acima de 1 Gbps.
