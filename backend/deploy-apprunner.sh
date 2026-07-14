#!/usr/bin/env bash
#
# One-shot backend deploy to AWS App Runner (Docker container, SSE streaming).
# Run from the backend/ directory with the AWS CLI + Docker configured.
#
# Usage:
#   ./deploy-apprunner.sh
#
# Optional env overrides:
#   REGION           default: us-west-2
#   SERVICE_NAME     default: stock-debate-backend
#   BEDROCK_MODEL_ID default: us.anthropic.claude-opus-4-8
#   BEDROCK_MODEL_ID_FALLBACK  default: us.anthropic.claude-sonnet-4-5-20250929-v1:0
#   LLM_PROVIDER     default: bedrock (use "mock" to deploy without Bedrock)
#   FINNHUB_API_KEY  default: (blank)
#   GNEWS_API_KEY    default: (blank)
#
set -euo pipefail

REGION="${REGION:-us-west-2}"
SERVICE_NAME="${SERVICE_NAME:-stock-debate-backend}"
LLM_PROVIDER="${LLM_PROVIDER:-bedrock}"
BEDROCK_MODEL_ID="${BEDROCK_MODEL_ID:-us.anthropic.claude-opus-4-8}"
BEDROCK_MODEL_ID_FALLBACK="${BEDROCK_MODEL_ID_FALLBACK:-us.anthropic.claude-sonnet-4-5-20250929-v1:0}"
FINNHUB_API_KEY="${FINNHUB_API_KEY:-}"
GNEWS_API_KEY="${GNEWS_API_KEY:-}"
REPO="${SERVICE_NAME}"

ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
echo "==> Account=$ACCOUNT  Region=$REGION  Service=$SERVICE_NAME"

if [[ ! -f Dockerfile || ! -d app ]]; then
  echo "ERROR: run this from the backend/ directory (needs Dockerfile + app/)." >&2
  exit 1
fi

# ===========================================================================
# 1. IAM roles (idempotent — skips if they exist)
# ===========================================================================
echo "==> Ensuring IAM roles..."

# Instance role (lets the container call Bedrock)
INSTANCE_ROLE="StockDebateAppRunnerInstanceRole"
aws iam get-role --role-name "$INSTANCE_ROLE" >/dev/null 2>&1 || {
  echo "    Creating instance role: $INSTANCE_ROLE"
  cat > /tmp/instance-trust.json <<'JSON'
{"Version":"2012-10-17","Statement":[{"Effect":"Allow",
  "Principal":{"Service":"tasks.apprunner.amazonaws.com"},"Action":"sts:AssumeRole"}]}
JSON
  aws iam create-role --role-name "$INSTANCE_ROLE" \
    --assume-role-policy-document file:///tmp/instance-trust.json >/dev/null
  cat > /tmp/bedrock-policy.json <<'JSON'
{"Version":"2012-10-17","Statement":[{"Sid":"BedrockInvoke","Effect":"Allow",
  "Action":["bedrock:InvokeModel","bedrock:InvokeModelWithResponseStream",
            "bedrock:Converse","bedrock:ConverseStream"],
  "Resource":["arn:aws:bedrock:*:*:inference-profile/us.anthropic.*",
              "arn:aws:bedrock:us-*::foundation-model/anthropic.*"]}]}
JSON
  aws iam put-role-policy --role-name "$INSTANCE_ROLE" \
    --policy-name BedrockInvoke --policy-document file:///tmp/bedrock-policy.json
}

# ECR access role (lets App Runner pull the image)
ECR_ROLE="AppRunnerECRAccessRole"
aws iam get-role --role-name "$ECR_ROLE" >/dev/null 2>&1 || {
  echo "    Creating ECR access role: $ECR_ROLE"
  cat > /tmp/ecr-trust.json <<'JSON'
{"Version":"2012-10-17","Statement":[{"Effect":"Allow",
  "Principal":{"Service":"build.apprunner.amazonaws.com"},"Action":"sts:AssumeRole"}]}
JSON
  aws iam create-role --role-name "$ECR_ROLE" \
    --assume-role-policy-document file:///tmp/ecr-trust.json >/dev/null
  aws iam attach-role-policy --role-name "$ECR_ROLE" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess
}

# ===========================================================================
# 2. ECR repository
# ===========================================================================
echo "==> Ensuring ECR repository: $REPO"
aws ecr create-repository --repository-name "$REPO" --region "$REGION" >/dev/null 2>&1 || true

# ===========================================================================
# 3. Build + push Docker image
# ===========================================================================
echo "==> Building Docker image..."
docker build -t "$REPO" .
echo "==> Pushing to ECR..."
aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"
docker tag "$REPO:latest" "$ACCOUNT.dkr.ecr.$REGION.amazonaws.com/$REPO:latest"
docker push "$ACCOUNT.dkr.ecr.$REGION.amazonaws.com/$REPO:latest"

# ===========================================================================
# 4. Create or update App Runner service
# ===========================================================================
ARN=$(aws apprunner list-services --region "$REGION" \
  --query "ServiceSummaryList[?ServiceName=='${SERVICE_NAME}'].ServiceArn | [0]" --output text 2>/dev/null)

ENV_BLOCK='"LLM_PROVIDER":"'"$LLM_PROVIDER"'","BEDROCK_MODEL_ID":"'"$BEDROCK_MODEL_ID"'","BEDROCK_MODEL_ID_FALLBACK":"'"$BEDROCK_MODEL_ID_FALLBACK"'","REQUIRE_AUTH":"false"'
[[ -n "$FINNHUB_API_KEY" ]] && ENV_BLOCK="$ENV_BLOCK,\"FINNHUB_API_KEY\":\"$FINNHUB_API_KEY\""
[[ -n "$GNEWS_API_KEY" ]] && ENV_BLOCK="$ENV_BLOCK,\"GNEWS_API_KEY\":\"$GNEWS_API_KEY\""

if [[ -z "$ARN" || "$ARN" == "None" ]]; then
  echo "==> Creating App Runner service: $SERVICE_NAME"
  cat > /tmp/apprunner-service.json <<JSON
{
  "ServiceName": "${SERVICE_NAME}",
  "SourceConfiguration": {
    "AuthenticationConfiguration": {
      "AccessRoleArn": "arn:aws:iam::${ACCOUNT}:role/${ECR_ROLE}"
    },
    "AutoDeploymentsEnabled": false,
    "ImageRepository": {
      "ImageIdentifier": "${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com/${REPO}:latest",
      "ImageRepositoryType": "ECR",
      "ImageConfiguration": {
        "Port": "8000",
        "RuntimeEnvironmentVariables": {${ENV_BLOCK}}
      }
    }
  },
  "InstanceConfiguration": {
    "Cpu": "1024", "Memory": "2048",
    "InstanceRoleArn": "arn:aws:iam::${ACCOUNT}:role/${INSTANCE_ROLE}"
  },
  "HealthCheckConfiguration": {
    "Protocol": "HTTP", "Path": "/api/health",
    "Interval": 10, "Timeout": 5, "HealthyThreshold": 1, "UnhealthyThreshold": 5
  }
}
JSON
  aws apprunner create-service --cli-input-json file:///tmp/apprunner-service.json --region "$REGION" >/dev/null
  ARN=$(aws apprunner list-services --region "$REGION" \
    --query "ServiceSummaryList[?ServiceName=='${SERVICE_NAME}'].ServiceArn | [0]" --output text)
else
  echo "==> Service exists — updating + deploying new image..."
  aws apprunner update-service --service-arn "$ARN" --region "$REGION" \
    --source-configuration '{
      "AuthenticationConfiguration": {"AccessRoleArn": "arn:aws:iam::'"$ACCOUNT"':role/'"$ECR_ROLE"'"},
      "ImageRepository": {
        "ImageIdentifier": "'"$ACCOUNT"'.dkr.ecr.'"$REGION"'.amazonaws.com/'"$REPO"':latest",
        "ImageRepositoryType": "ECR",
        "ImageConfiguration": {"Port": "8000", "RuntimeEnvironmentVariables": {'"$ENV_BLOCK"'}}
      }
    }' >/dev/null
fi

# ===========================================================================
# 5. Wait for RUNNING + print URL
# ===========================================================================
echo "==> Waiting for service to reach RUNNING state (~3-5 min)..."
while true; do
  STATUS=$(aws apprunner describe-service --service-arn "$ARN" --region "$REGION" \
    --query 'Service.Status' --output text)
  if [[ "$STATUS" == "RUNNING" ]]; then break; fi
  if [[ "$STATUS" == "CREATE_FAILED" || "$STATUS" == "DELETE_FAILED" ]]; then
    echo "ERROR: Service status is $STATUS. Check CloudWatch logs." >&2; exit 1
  fi
  echo "    status: $STATUS ..."
  sleep 15
done

URL=$(aws apprunner describe-service --service-arn "$ARN" --region "$REGION" \
  --query 'Service.ServiceUrl' --output text)

echo ""
echo "==> Deployed! App Runner URL:"
echo "    https://${URL}"
echo ""
echo "    Health:  curl -s https://${URL}/api/health"
echo "    Debate:  curl -sN 'https://${URL}/api/debate/stream?ticker=AAPL&agents=fundamental,chartist&rounds=1'"
echo ""
echo "    Set the frontend build env:"
echo "      VITE_API_BASE=https://${URL}"
echo "      VITE_TRANSPORT=sse"
