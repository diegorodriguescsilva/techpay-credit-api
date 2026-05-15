# TechPay Credit API - Cloud Run 

> Pipeline CI/CD blindado com segurança de nível bancário no Google Cloud Platform.

---

## Sumário

- [Sobre o Projeto](#sobre-o-projeto)
- [O Problema](#o-problema)
- [A Solução](#a-solução)
- [Arquitetura](#arquitetura)
- [Estrutura do Repositório](#estrutura-do-repositório)
- [Pré-requisitos](#pré-requisitos)
- [Infraestrutura GCP](#infraestrutura-gcp)
- [Pipeline CI/CD](#pipeline-cicd)
- [Segurança](#segurança)
- [Como Testar](#como-testar)
- [Comandos Úteis](#comandos-úteis)
- [Definition of Done](#definition-of-done)

---

## Sobre o Projeto

A **TechPay Credit API** é um serviço de verificação de crédito construído com Flask e implantado no Google Cloud Run. O projeto foi desenvolvido como resposta a um relatório de auditoria de segurança que identificou vulnerabilidades críticas na infraestrutura original.

O foco não é apenas a aplicação em si, mas a **esteira de CI/CD blindada** que a envolve — automatizando o ciclo de vida completo com segurança de nível bancário.

---

## O Problema

A auditoria identificou três vulnerabilidades críticas:

| Vulnerabilidade | Descrição |
|---|---|
| **Deploy manual** | Qualquer atualização em produção dependia de execução manual de comandos — sem automação, sem rastreabilidade, propenso a erros humanos |
| **Chave no código** | Credenciais de API armazenadas diretamente no repositório Git — visíveis para qualquer pessoa com acesso ao código-fonte |
| **Rede sem controle** | A aplicação se comunicava com qualquer servidor na internet pública — sem filtros, sem auditoria, sem controle de egress |

---

## A Solução

| Vulnerabilidade | Solução Implementada |
|---|---|
| Deploy manual | Cloud Build Trigger — qualquer `git push` na `main` dispara o pipeline automaticamente |
| Chave no código | Secret Manager — valor injetado em runtime, nunca armazenado no repositório |
| Rede sem controle | VPC Connector com `--vpc-egress=all-traffic` — todo tráfego passa pela rede privada |

---

## Arquitetura

```
DEV                        GCP CLOUD BUILD                    GCP SERVICES
 │                               │                                  │
 │── git push origin main ──────▶│                                  │
 │                               │── Step 0: docker build ─────────▶│
 │                               │── Step 1: docker push ──────────▶ Artifact Registry
 │                               │── Step 2: gcloud run deploy ────▶ Cloud Run
 │                               │                                  │
 │                               │                           ┌──────┴──────┐
 │                               │                           │  credit-api │
 │                               │                           │             │
 │                               │                    sa-credit-api        │
 │                               │                    Secret Manager       │
 │                               │                    VPC Connector        │
 │                               │                           └─────────────┘
 │                               │                                  │
USUÁRIO                          │                                  │
 │── GET /v1/credit-check ───────────────────────────────────────▶  │
 │◀─ 403 Forbidden (sem token) ──────────────────────────────────   │
 │◀─ JSON (com token válido) ────────────────────────────────────   │
```

---

## Estrutura do Repositório

```
techpay-credit-api/
├── main.py            # Aplicação Flask
├── requirements.txt   # Dependências Python
├── Dockerfile         # Empacotamento da imagem
└── cloudbuild.yaml    # Configuração do pipeline CI/CD
```

---

## Pré-requisitos

- Conta no Google Cloud Platform
- `gcloud` CLI instalado e autenticado
- Docker instalado (para testes locais)
- Python 3.11+
- Repositório conectado ao Cloud Build via GitHub App

---

## Infraestrutura GCP

### Variáveis de ambiente

```bash
export PROJECT_ID="tbx-diego-rodrigues"
export REGION="us-central1"
export REPO_NAME="techpay-repo"
export SA_BUILD="sa-cloud-build"
export SA_APP="sa-credit-api"
export VPC_CONNECTOR="vpc-connector-techpay"
```

### 1. Habilitar APIs

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  vpcaccess.googleapis.com \
  --project=$PROJECT_ID
```

### 2. Artifact Registry

Repositório privado Docker para armazenamento das imagens tagueadas:

```bash
gcloud artifacts repositories create $REPO_NAME \
  --repository-format=docker \
  --location=$REGION \
  --description="TechPay Credit API - imagens privadas" \
  --project=$PROJECT_ID
```

### 3. Service Accounts

Duas identidades separadas — cada uma com apenas as permissões necessárias:

#### `sa-cloud-build` — executa o pipeline

```bash
gcloud iam service-accounts create $SA_BUILD \
  --display-name="Cloud Build Service Account" \
  --project=$PROJECT_ID

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${SA_BUILD}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/cloudbuild.builds.builder"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${SA_BUILD}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${SA_BUILD}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${SA_BUILD}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${SA_BUILD}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/logging.logWriter"
```

#### `sa-credit-api` — roda a aplicação

```bash
gcloud iam service-accounts create $SA_APP \
  --display-name="Credit API Service Account" \
  --project=$PROJECT_ID

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${SA_APP}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/logging.logWriter"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${SA_APP}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/monitoring.metricWriter"
```

### 4. Secret Manager

```bash
# Cria o segredo
echo -n "sua-chave-aqui" | \
  gcloud secrets create CREDIT_API_KEY \
  --data-file=- \
  --replication-policy="automatic" \
  --project=$PROJECT_ID

# Dá acesso SOMENTE para sa-credit-api
gcloud secrets add-iam-policy-binding CREDIT_API_KEY \
  --member="serviceAccount:${SA_APP}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor" \
  --project=$PROJECT_ID
```

### 5. VPC Connector

```bash
gcloud compute networks vpc-access connectors create $VPC_CONNECTOR \
  --network=default \
  --region=$REGION \
  --range="10.8.0.0/28" \
  --project=$PROJECT_ID

# Confirma que está READY
gcloud compute networks vpc-access connectors describe $VPC_CONNECTOR \
  --region=$REGION \
  --project=$PROJECT_ID
```

### 6. Cloud Build Trigger

```bash
gcloud builds triggers create github \
  --name="trigger-credit-api-main" \
  --repo-owner="diegorodriguescsilva" \
  --repo-name="techpay-credit-api" \
  --branch-pattern="^main$" \
  --build-config="cloudbuild.yaml" \
  --service-account="projects/${PROJECT_ID}/serviceAccounts/${SA_BUILD}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --substitutions="_REGION=${REGION},_REPO_NAME=${REPO_NAME},_VPC_CONNECTOR=${VPC_CONNECTOR}" \
  --region=$REGION \
  --project=$PROJECT_ID
```

---

## Pipeline CI/CD

O arquivo `cloudbuild.yaml` define os 3 steps executados automaticamente a cada `git push` na branch `main`:

```yaml
steps:
  # Step 0: Build da imagem com tag do commit
  - name: "gcr.io/cloud-builders/docker"
    args:
      - "build"
      - "-t"
      - "${_REGION}-docker.pkg.dev/${PROJECT_ID}/${_REPO_NAME}/credit-api:${SHORT_SHA}"
      - "-t"
      - "${_REGION}-docker.pkg.dev/${PROJECT_ID}/${_REPO_NAME}/credit-api:latest"
      - "."

  # Step 1: Push para o Artifact Registry
  - name: "gcr.io/cloud-builders/docker"
    args:
      - "push"
      - "--all-tags"
      - "${_REGION}-docker.pkg.dev/${PROJECT_ID}/${_REPO_NAME}/credit-api"

  # Step 2: Deploy no Cloud Run
  - name: "gcr.io/google.com/cloudsdktool/cloud-sdk"
    entrypoint: "gcloud"
    args:
      - "run"
      - "deploy"
      - "credit-api"
      - "--image=${_REGION}-docker.pkg.dev/${PROJECT_ID}/${_REPO_NAME}/credit-api:${SHORT_SHA}"
      - "--region=${_REGION}"
      - "--service-account=sa-credit-api@${PROJECT_ID}.iam.gserviceaccount.com"
      - "--update-secrets=CREDIT_API_KEY=CREDIT_API_KEY:latest"
      - "--vpc-connector=${_VPC_CONNECTOR}"
      - "--vpc-egress=all-traffic"
      - "--min-instances=1"
      - "--no-allow-unauthenticated"
      - "--set-env-vars=REVISION_TAG=${SHORT_SHA}"
      - "--platform=managed"

substitutions:
  _REGION: "us-central1"
  _REPO_NAME: "techpay-repo"
  _VPC_CONNECTOR: "vpc-connector-techpay"

options:
  logging: CLOUD_LOGGING_ONLY
```

### Flags do deploy e seus critérios

| Flag | Critério Atendido |
|---|---|
| `--service-account` | SA customizada — não usa a conta padrão |
| `--update-secrets` | Segredo injetado do Secret Manager em runtime |
| `--vpc-connector` | Serviço associado ao VPC Connector |
| `--vpc-egress=all-traffic` | Todo egress forçado pela VPC — sem internet pública |
| `--min-instances=1` | Zero cold start — sempre 1 instância ativa |
| `--no-allow-unauthenticated` | Acesso anônimo retorna 403 Forbidden |
| `--set-env-vars=REVISION_TAG` | Hash do commit injetado para rastreabilidade |

---

## Segurança

### Princípio do Menor Privilégio

```
sa-cloud-build
  ├── roles/cloudbuild.builds.builder    (projeto)
  ├── roles/artifactregistry.writer      (projeto)
  ├── roles/run.admin                    (projeto)
  ├── roles/iam.serviceAccountUser       (projeto)
  └── roles/logging.logWriter            (projeto)

sa-credit-api
  ├── roles/logging.logWriter            (projeto)
  ├── roles/monitoring.metricWriter      (projeto)
  └── roles/secretmanager.secretAccessor (somente no segredo CREDIT_API_KEY)
```

### Fluxo do Segredo

```
Secret Manager
  └── CREDIT_API_KEY (criptografado)
        └── somente sa-credit-api pode ler
              └── Cloud Run injeta como variável de ambiente em runtime
                    └── main.py lê via os.environ.get("CREDIT_API_KEY")
                          └── valor NUNCA aparece no código ou nos logs
```

### Controle de Rede

```
sem VPC Connector:
  Cloud Run ──▶ internet pública (sem controle)

com VPC Connector + all-traffic:
  Cloud Run ──▶ vpc-connector-techpay ──▶ VPC privada (controlado e auditável)
```

---

## Como Testar

### Pegar a URL do serviço

```bash
export SERVICE_URL=$(gcloud run services describe credit-api \
  --region=us-central1 \
  --format="value(status.url)" \
  --project=tbx-diego-rodrigues)

echo $SERVICE_URL
```

### Teste 1 — Acesso anônimo (deve retornar 403)

```bash
curl -i $SERVICE_URL/v1/credit-check
```

Resposta esperada:
```
HTTP/2 403 Forbidden
```

### Teste 2 — Acesso autenticado (deve retornar JSON)

```bash
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  $SERVICE_URL/v1/credit-check
```

Resposta esperada:
```json
{
  "service": "credit-api",
  "status": "active",
  "vault_access": true,
  "revision_tag": "e7e0c34"
}
```

| Campo | Significado |
|---|---|
| `vault_access: true` | Secret Manager funcionando — segredo foi injetado corretamente |
| `revision_tag: e7e0c34` | Hash do commit em produção — rastreabilidade ativa |

### Teste pelo navegador

Instale a extensão **ModHeader** no Chrome:

1. Gere um token: `gcloud auth print-identity-token`
2. No ModHeader, adicione o header: `Authorization: Bearer SEU_TOKEN`
3. Acesse: `$SERVICE_URL/v1/credit-check`

> ⚠️ O token expira em 1 hora. Se der 403 com o ModHeader ativo, gere um novo token.

---

## Comandos Úteis

### Ver status do serviço

```bash
gcloud run services describe credit-api \
  --region=us-central1 \
  --project=tbx-diego-rodrigues \
  --format="yaml"
```

### Ver revisões do serviço

```bash
gcloud run revisions list \
  --service=credit-api \
  --region=us-central1 \
  --project=tbx-diego-rodrigues
```

### Ver histórico de builds

```bash
gcloud builds list \
  --project=tbx-diego-rodrigues \
  --limit=5
```

### Ver imagens no Artifact Registry

```bash
gcloud artifacts docker images list \
  us-central1-docker.pkg.dev/tbx-diego-rodrigues/techpay-repo/credit-api
```

### Desativar o serviço (economizar custos)

```bash
# Zerar instâncias
gcloud run services update credit-api \
  --min-instances=0 \
  --region=us-central1 \
  --project=tbx-diego-rodrigues

# Deletar VPC Connector
gcloud compute networks vpc-access connectors delete vpc-connector-techpay \
  --region=us-central1 \
  --project=tbx-diego-rodrigues
```

### Reativar o serviço

```bash
# Recriar VPC Connector (~2 minutos)
gcloud compute networks vpc-access connectors create vpc-connector-techpay \
  --network=default \
  --region=us-central1 \
  --range="10.8.0.0/28" \
  --project=tbx-diego-rodrigues

# Reativar instâncias
gcloud run services update credit-api \
  --min-instances=1 \
  --region=us-central1 \
  --project=tbx-diego-rodrigues
```

### Tornar público (temporário)

```bash
gcloud run services add-iam-policy-binding credit-api \
  --region=us-central1 \
  --member="allUsers" \
  --role="roles/run.invoker" \
  --project=tbx-diego-rodrigues
```

### Reverter para privado

```bash
gcloud run services remove-iam-policy-binding credit-api \
  --region=us-central1 \
  --member="allUsers" \
  --role="roles/run.invoker" \
  --project=tbx-diego-rodrigues
```

---

## Definition of Done

### Automação e Pipeline
- [x] `git push` na branch `main` dispara o build e o deploy automaticamente
- [x] Imagens armazenadas no Artifact Registry privado, tagueadas com `$SHORT_SHA`
- [x] Pipeline declarativo completo no `cloudbuild.yaml` (Build, Push e Deploy)

### Segurança e Identidade
- [x] API rodando sob Service Account customizada `sa-credit-api`
- [x] `CREDIT_API_KEY` injetada diretamente do Secret Manager
- [x] Somente `sa-credit-api` tem permissão de leitura sobre o segredo

### Conectividade e Rede
- [x] Serviço associado ao Serverless VPC Access Connector `vpc-connector-techpay`
- [x] Todo tráfego de saída forçado via VPC (`--vpc-egress=all-traffic`)

### Disponibilidade e Acesso
- [x] Mínimo de 1 instância ativa permanentemente (zero cold start)
- [x] Acesso anônimo retorna `403 Forbidden`
- [x] Variável `REVISION_TAG` com hash do commit configurada

---

*Diego Rodrigues • tbx-diego-rodrigues • Google Cloud Platform • Maio 2026*
