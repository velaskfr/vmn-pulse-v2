# VMN Pulse — Monitoramento de Equipamentos da Rede Local

Aplicação simples para cadastrar equipamentos da rede (switches, APs, PCs, NVR, etc.),
monitorá-los via ping em intervalos regulares, visualizar status em uma tabela estilo
planilha, ver histórico/log de cada equipamento e receber alertas no Discord quando
algo cai ou fica lento.

Pensada para o cenário de ~100 equipamentos numa rede local (ex: academia com AP's
UniFi), para ajudar a mapear origem de quedas/lentidão.

## O que a aplicação faz

- Cadastro de equipamentos: Nome, IP, MAC, Localização (curta).
- Ping automático a cada `PING_INTERVAL_SECONDS` (padrão 60s), enviando `PING_COUNT`
  pacotes ICMP por ciclo (padrão 4), com concorrência limitada
  (`PING_CONCURRENCY`, padrão 20 hosts simultâneos) para não gerar rajada na rede.
- Colunas de RTT último, média/mín/máx da última 1h, perda % da última 1h,
  disponibilidade das últimas 24h.
- Status colorido: verde = Ativo / amarelo = Lento (perda ou latência acima do
  limite) / vermelho = Offline (sem resposta).
- Histerese simples: só marca como "offline" depois de `OFFLINE_CONFIRM_CYCLES`
  ciclos ruins seguidos (padrão 2 = ~2 minutos), pra não alarmar por causa de
  uma perda de pacote pontual. Volta pra "online" assim que responder de novo.
- Coluna "Desde quando" (tempo desde a última mudança de status) e "Tempo offline"
  (só quando está offline).
- Botão "Ver log" por equipamento: abre o histórico recente de pings e o
  histórico de mudanças de status (quando caiu, quando voltou).
- Alertas no Discord via webhook, disparados só nas transições de status
  (não fica repetindo a cada minuto).
- Segunda página: gráfico de disponibilidade (%) e latência média por hora,
  por equipamento, período configurável (24h / 7 dias / 30 dias).
- Login simples (usuário/senha + JWT) protegendo toda a aplicação.

## Como rodar

Pré-requisitos: Docker e Docker Compose instalados no servidor onde vai hospedar.

```bash
cp .env.example .env
# edite o .env: troque as senhas, defina o SECRET_KEY, e opcionalmente
# cole a URL do webhook do Discord em DISCORD_WEBHOOK_URL

docker compose up -d --build
```

Acesse `http://IP-DO-SERVIDOR:8000`. Faça login com o usuário/senha definidos em
`ADMIN_USER` / `ADMIN_PASSWORD` no `.env` (esse usuário é criado automaticamente
na primeira vez que o app sobe).

> Importante: como o ping ICMP precisa de permissão especial, o `docker-compose.yml`
> já adiciona as capabilities `NET_RAW` e `NET_ADMIN` ao container do app. Isso é
> necessário e seguro (não expõe nada externamente, só permite abrir socket ICMP).

## Como criar o webhook do Discord

1. No canal do Discord onde você quer receber os alertas: Configurações do canal →
   Integrações → Webhooks → Novo Webhook.
2. Copie a URL do webhook e cole em `DISCORD_WEBHOOK_URL` no `.env`.
3. Reinicie: `docker compose up -d` (ou `docker compose restart app`).

Sem webhook configurado, a aplicação funciona normalmente, só não envia
notificação — tudo continua registrado na tela e no log.

## Sobre os parâmetros de monitoramento (`.env`)

| Variável | Padrão | O que faz |
|---|---|---|
| `PING_INTERVAL_SECONDS` | 60 | Intervalo entre ciclos de ping |
| `PING_COUNT` | 4 | Pacotes ICMP por equipamento a cada ciclo |
| `PING_CONCURRENCY` | 20 | Quantos equipamentos são pingados ao mesmo tempo |
| `LATENCY_WARN_MS` | 100 | Acima disso, status vira "Lento" (pode ser sobrescrito por equipamento) |
| `LOSS_WARN_PCT` | 20 | Perda % acima disso também vira "Lento" |
| `OFFLINE_CONFIRM_CYCLES` | 2 | Ciclos ruins seguidos para confirmar "Offline" |

Para ~100 equipamentos, com concorrência 20 e 4 pacotes por host, um ciclo
completo leva poucos segundos — bem dentro da janela de 60s, sem sobrecarregar
a rede.

## Estrutura do projeto

```
netmonitor/
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py            # app FastAPI, startup, rotas estáticas
│       ├── config.py          # configurações via variáveis de ambiente
│       ├── database.py        # conexão com Postgres (SQLAlchemy)
│       ├── models.py          # tabelas: Device, PingResult, AlertEvent, User
│       ├── schemas.py         # validação/serialização (Pydantic)
│       ├── security.py        # login, hash de senha, JWT
│       ├── ping_service.py    # execução dos pings (icmplib, assíncrono)
│       ├── scheduler.py       # loop de fundo: pinga tudo a cada X segundos
│       ├── discord_alert.py   # envio de alerta via webhook
│       └── routers/
│           ├── auth.py
│           ├── devices.py     # CRUD de equipamentos
│           └── monitoring.py  # tabela de status, histórico, disponibilidade
│   └── static/                # frontend (HTML/CSS/JS puro, sem build)
│       ├── login.html
│       ├── index.html         # tabela principal estilo planilha
│       ├── device.html        # gráficos de disponibilidade
│       ├── css/style.css
│       └── js/{api,dashboard,device}.js
```

## Ideias para evoluir (não implementadas ainda)

- **Telegram/WhatsApp**: dá pra adicionar do mesmo jeito que o Discord —
  um bot do Telegram é tão simples quanto o webhook; WhatsApp geralmente exige
  uma API paga (Twilio, Meta Cloud API) ou um gateway tipo Evolution API.
- **Exportar CSV/Excel** da tabela ou do histórico de um equipamento.
- **Botão de manutenção**: marcar um equipamento como "em manutenção" pra pausar
  alertas sem excluir o cadastro (já existe o campo `is_active` no banco, só
  falta um botão na tela pra alternar).
- **Agrupar por localização/setor** na tabela (ex: todos os APs de um mesmo
  bloco), útil pra identificar se a queda é por região da academia.
- **Traceroute/MTR sob demanda** a partir do botão de log, pra investigar picos
  de latência específicos.
- **Retenção de dados**: o histórico de ping cresce (100 equipamentos × 1 ping/min
  ≈ 144 mil linhas/dia). Vale criar uma rotina simples de limpeza (ex: manter
  detalhe de 30 dias e, depois disso, só os agregados por hora).
- **Multiusuário com permissões** (ex: um usuário só visualiza, outro edita).
- **Correlação entre equipamentos**: comparar horários de queda entre vários
  equipamentos da mesma área pra identificar se é o mesmo AP/switch/uplink
  causando o problema (bem alinhado com o caso do TX-Retries do UniFi que
  você já vinha investigando).
