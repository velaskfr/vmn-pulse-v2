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

## Rodar em Raspberry Pi (appliance dedicado)

Para instalar num Raspberry Pi 4 como appliance de monitoramento (com boot por
SSD USB, que é o setup recomendado), veja o guia dedicado:
[**RASPBERRY-PI.md**](RASPBERRY-PI.md).

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

## Novidades da V2

- **Botão de manutenção** (⏸/▶ na coluna Ações): pausa ping e alertas do
  equipamento sem excluir o cadastro. Status vira "Manutenção" (roxo).
- **Exportar CSV**: botão na toolbar exporta a tabela inteira; dentro do log
  de cada equipamento dá pra exportar o histórico de 24h. CSV com `;` e BOM,
  abre direto no Excel brasileiro.
- **Agrupar por local**: checkbox na toolbar agrupa a tabela por localização,
  com contadores de offline/lentos por grupo.
- **Traceroute sob demanda**: aba no modal de log executa traceroute até o
  equipamento direto do servidor, pra investigar onde a latência estoura.
- **Correlação de quedas** (`/correlation.html`): agrupa eventos de queda/lentidão
  em janelas de tempo (2/5/10 min) e mostra quedas simultâneas — se vários
  equipamentos caem juntos, a origem provável é o ponto em comum (AP, switch,
  uplink). Inclui ranking de eventos por localização.
- **Retenção de dados**: uma vez por dia, pings mais antigos que
  `RETENTION_DETAIL_DAYS` (padrão 30) são compactados em agregados por hora
  (tabela `ping_hourly`) e removidos do detalhe. Os gráficos de disponibilidade
  seguem funcionando com o histórico antigo, só que agregado.
- **Multiusuário com papéis**: administradores gerenciam equipamentos e usuários;
  visualizadores só consultam. Gestão pelo botão "Usuários" na toolbar (admin).
  Bancos criados na V1 são migrados automaticamente no startup.

## Monitor de qualidade da internet (speedtest)

Página **🌐 Internet** na toolbar: mostra status atual (Normal/Lenta/Falha),
cards de download, upload e ping, gráficos históricos e tabela de testes.

- Teste automático a cada `SPEEDTEST_INTERVAL_MINUTES` (padrão 10 min).
  **Atenção:** cada speedtest consome banda real (pode passar de 100 MB em
  links rápidos) e satura o link por ~30s, o que afeta momentaneamente os
  pings dos equipamentos. Em produção, considere 30 ou 60 min.
- Limites configuráveis: `SPEEDTEST_MIN_DOWNLOAD_MBPS`, `SPEEDTEST_MIN_UPLOAD_MBPS`,
  `SPEEDTEST_MAX_PING_MS`. Ajuste para o plano contratado do link (ex: plano de
  500 Mbps → mínimo 350 já indica degradação).
- Alerta no Discord nas transições (Normal → Lenta, Lenta → Normal, falha),
  seguindo a mesma lógica dos equipamentos.
- Botão "Testar agora" (admin) dispara um teste manual.
- Dica complementar: cadastre um IP externo (8.8.8.8 ou 1.1.1.1) como
  equipamento com localização "WAN" — o ping por minuto mede latência/perda
  do link continuamente, sem consumir banda.

## Ideias para evoluir

- **Telegram**: tão simples quanto o Discord (bot + chat_id). WhatsApp exige
  API paga (Twilio, Meta Cloud API) ou gateway tipo Evolution API.
- **MTR contínuo** e gráficos de perda por hop.
- **Notificação de recuperação com duração da queda** ("voltou após 12min").
