# Deployment Guide

Two-part deploy on native AWS:
- **Backend → AWS App Runner** (Docker container, streams SSE, no request timeout)
- **Frontend → CloudFront + S3** (private bucket via Origin Access Control)

Both have one-shot scripts. You need an AWS account, the AWS CLI configured, and
Docker installed. Region defaults to `us-west-2`.

---

## Prerequisites (one-time)

1. **Enable Bedrock model access** — in the AWS Bedrock console → *Model access*
   (in your region), enable the Anthropic Claude models (Opus 4.8 + Sonnet 4.5).
   Without this, the debate falls back or fails.
2. **AWS CLI + Docker** working locally (`aws sts get-caller-identity` succeeds,
   `docker ps` works).

The backend deploy script creates the two IAM roles it needs automatically:
- **Instance role** (`StockDebateAppRunnerInstanceRole`) — lets the container call Bedrock.
- **ECR access role** (`AppRunnerECRAccessRole`) — lets App Runner pull the image.

---

## 1. Backend → AWS App Runner

### One-shot script (recommended)
```bash
cd backend
FINNHUB_API_KEY=xxx GNEWS_API_KEY=yyy ./deploy-apprunner.sh
```
The script:
1. Creates the IAM roles (idempotent — skips if they exist)
2. Creates the ECR repository
3. `docker build` + pushes the image to ECR
4. Creates the App Runner service (or updates + redeploys if it exists)
5. Waits for `RUNNING`
6. Prints the service URL + the `VITE_API_BASE` to set for the frontend

Optional env overrides: `REGION`, `SERVICE_NAME`, `LLM_PROVIDER` (use `mock` to
deploy without Bedrock), `BEDROCK_MODEL_ID`, `BEDROCK_MODEL_ID_FALLBACK`.

### Redeploy after changes — IMPORTANT
- **Code change** → rebuild + push the image, then trigger a deploy:
  ```bash
  REGION=us-west-2; ACCOUNT=$(aws sts get-caller-identity --query Account --output text); REPO=stock-debate-backend
  docker build -t $REPO backend
  aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ACCOUNT.dkr.ecr.$REGION.amazonaws.com
  docker tag $REPO:latest $ACCOUNT.dkr.ecr.$REGION.amazonaws.com/$REPO:latest
  docker push $ACCOUNT.dkr.ecr.$REGION.amazonaws.com/$REPO:latest
  ARN=$(aws apprunner list-services --region $REGION --query "ServiceSummaryList[?ServiceName=='stock-debate-backend'].ServiceArn" --output text)
  aws apprunner start-deployment --service-arn $ARN --region $REGION
  ```
- **Env-var-only change** → `aws apprunner update-service ... --source-configuration '{...}'`
  with the new env block. (`update-service` applies env; `start-deployment` only
  pulls the image — don't confuse them.)

### Verify
```bash
ARN=$(aws apprunner list-services --region us-west-2 \
  --query "ServiceSummaryList[?ServiceName=='stock-debate-backend'].ServiceArn" --output text)
URL=$(aws apprunner describe-service --service-arn $ARN --region us-west-2 --query 'Service.ServiceUrl' --output text)
curl -s https://$URL/api/health
curl -s "https://$URL/api/stock/NSE:TCS" | head -c 200   # expect source":"yahoo", INR
```

---

## 2. Frontend → CloudFront + S3

### One-shot script
```bash
cd frontend
VITE_API_BASE=https://<your-apprunner-url> ./deploy-cloudfront.sh
```
The script builds the SPA, creates a private S3 bucket, uploads the build,
creates a CloudFront distribution with Origin Access Control (the bucket stays
private) and SPA routing (403/404 → index.html), and prints the CloudFront URL.

- First deploy takes ~5–15 min to propagate DNS/edge.
- The backend CORS already allows `*.cloudfront.net`, so the SPA can call the
  API cross-origin. For a custom domain, set `CORS_ORIGIN_REGEX` on the backend.
- Re-running the script re-uploads and invalidates the CloudFront cache.

### Any other static host
```bash
cd frontend
VITE_API_BASE=https://<backend-url> npm run build
# serve the build/ folder on Netlify, nginx, S3 website hosting, etc.
```

---

## Optional: gate the API behind login (OIDC)

By default the API is open (good for a public demo). To require a login, set on
the backend:
```
REQUIRE_AUTH=true
OIDC_ISSUER=https://<your-provider>/         # e.g. Cognito/Auth0/Okta issuer
OIDC_JWKS_URL=https://<your-provider>/.well-known/jwks.json
OIDC_AUDIENCE=<your-client-id>               # optional
```
The frontend obtains an id_token (see `frontend/src/auth.ts` — wire `beginSso()`
to your provider, or pass `VITE_AUTH_TOKEN` for testing) and sends it as
`Authorization: Bearer <token>` (or `?access_token=` for the SSE stream).

---

## Cost notes
- **Bedrock** is ~95% of cost — pay per token. The backend caches identical LLM
  calls (see `data/cache.py`) to cut repeat cost.
- **App Runner** — small always-on cost for the running instance (1 vCPU / 2 GB).
- **CloudFront + S3** — pennies for a low-traffic app (mostly free-tier).
- **Yahoo / NSE / Finnhub / GNews** — free tiers; no cost.

## Teardown
```bash
REGION=us-west-2; ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
# App Runner
ARN=$(aws apprunner list-services --region $REGION --query "ServiceSummaryList[?ServiceName=='stock-debate-backend'].ServiceArn" --output text)
aws apprunner delete-service --service-arn $ARN --region $REGION
# ECR
aws ecr delete-repository --repository-name stock-debate-backend --force --region $REGION
# CloudFront: disable → wait until Deployed → delete (see AWS docs)
# S3
aws s3 rb s3://stock-debate-frontend-$ACCOUNT --force
# IAM roles
aws iam delete-role-policy --role-name StockDebateAppRunnerInstanceRole --policy-name BedrockInvoke
aws iam delete-role --role-name StockDebateAppRunnerInstanceRole
aws iam detach-role-policy --role-name AppRunnerECRAccessRole --policy-arn arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess
aws iam delete-role --role-name AppRunnerECRAccessRole
```
