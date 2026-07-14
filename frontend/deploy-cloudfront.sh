#!/usr/bin/env bash
#
# Deploy the frontend as a static site on S3 + CloudFront.
# The backend stays on App Runner; the SPA calls it cross-origin (backend CORS
# already allows *.cloudfront.net).
#
# Run from the frontend/ directory (needs the built ./build or ./dist folder).
# Usage:
#   VITE_API_BASE=https://<apprunner-url> ./deploy-cloudfront.sh
#
set -euo pipefail

REGION="${REGION:-us-west-2}"
BUCKET="${BUCKET:-stock-debate-frontend-$(aws sts get-caller-identity --query Account --output text)}"
API_BASE="${VITE_API_BASE:?set VITE_API_BASE to your backend URL, e.g. https://xxxx.awsapprunner.com}"
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)

# --- 1. Build the SPA pointing at the App Runner backend, SSE transport -------
echo "==> Building frontend (API base: $API_BASE)"
cat > .env.production <<EOF
VITE_API_BASE=${API_BASE}
VITE_TRANSPORT=sse
EOF
# Clean install: remove any stale node_modules/lockfile (a partially-copied
# node_modules can leave a broken tsc; a stale lockfile may reference deps
# not on the public registry).
rm -rf node_modules package-lock.json
npm install
npm run build
# Vite outputs to ./build (see vite.config.ts). Fall back to ./dist if needed.
OUT="build"; [ -d "$OUT" ] || OUT="dist"
echo "    built into ./$OUT"

# --- 2. Create a PRIVATE S3 bucket (served only via CloudFront + OAC) ---------
echo "==> Ensuring S3 bucket: $BUCKET"
if ! aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  if [ "$REGION" = "us-east-1" ]; then
    aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" >/dev/null
  else
    aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" \
      --create-bucket-configuration "LocationConstraint=${REGION}" >/dev/null
  fi
fi

# --- 3. Upload the build ------------------------------------------------------
echo "==> Uploading site to S3"
# hashed assets: cache forever; index.html: never cache (so new deploys show up)
aws s3 sync "$OUT" "s3://${BUCKET}" --delete \
  --exclude index.html --cache-control "public,max-age=31536000,immutable"
aws s3 cp "$OUT/index.html" "s3://${BUCKET}/index.html" \
  --cache-control "no-cache,no-store,must-revalidate"

# --- 4. Origin Access Control (CloudFront → private S3) -----------------------
echo "==> Ensuring Origin Access Control"
OAC_ID=$(aws cloudfront list-origin-access-controls \
  --query "OriginAccessControlList.Items[?Name=='stock-debate-oac'].Id | [0]" --output text 2>/dev/null)
if [ -z "$OAC_ID" ] || [ "$OAC_ID" = "None" ]; then
  OAC_ID=$(aws cloudfront create-origin-access-control \
    --origin-access-control-config \
      "Name=stock-debate-oac,SigningProtocol=sigv4,SigningBehavior=always,OriginAccessControlOriginType=s3" \
    --query 'OriginAccessControl.Id' --output text)
fi
echo "    OAC: $OAC_ID"

# --- 5. Create the CloudFront distribution (if not already present) -----------
DIST_ID=$(aws cloudfront list-distributions \
  --query "DistributionList.Items[?Comment=='stock-debate-frontend'].Id | [0]" --output text 2>/dev/null)

if [ -z "$DIST_ID" ] || [ "$DIST_ID" = "None" ]; then
  echo "==> Creating CloudFront distribution"
  S3_DOMAIN="${BUCKET}.s3.${REGION}.amazonaws.com"
  CACHE_OPTIMIZED="658327ea-f89d-4fab-a63d-7e88639e58f6"  # managed CachingOptimized
  cat > /tmp/cf-fe.json <<JSON
{
  "CallerReference": "stock-debate-frontend-init",
  "Comment": "stock-debate-frontend",
  "Enabled": true,
  "DefaultRootObject": "index.html",
  "Origins": { "Quantity": 1, "Items": [{
    "Id": "s3-origin",
    "DomainName": "${S3_DOMAIN}",
    "OriginAccessControlId": "${OAC_ID}",
    "S3OriginConfig": { "OriginAccessIdentity": "" }
  }]},
  "DefaultCacheBehavior": {
    "TargetOriginId": "s3-origin",
    "ViewerProtocolPolicy": "redirect-to-https",
    "AllowedMethods": { "Quantity": 2, "Items": ["GET","HEAD"] },
    "CachePolicyId": "${CACHE_OPTIMIZED}",
    "Compress": true
  },
  "CustomErrorResponses": { "Quantity": 2, "Items": [
    { "ErrorCode": 403, "ResponseCode": "200", "ResponsePagePath": "/index.html", "ErrorCachingMinTTL": 10 },
    { "ErrorCode": 404, "ResponseCode": "200", "ResponsePagePath": "/index.html", "ErrorCachingMinTTL": 10 }
  ]}
}
JSON
  DIST_JSON=$(aws cloudfront create-distribution --distribution-config file:///tmp/cf-fe.json)
  DIST_ID=$(echo "$DIST_JSON" | python3 -c "import sys,json;print(json.load(sys.stdin)['Distribution']['Id'])")

  # Allow this distribution to read the private bucket.
  cat > /tmp/bucket-policy.json <<JSON
{ "Version": "2012-10-17", "Statement": [{
  "Sid": "AllowCloudFront", "Effect": "Allow",
  "Principal": { "Service": "cloudfront.amazonaws.com" },
  "Action": "s3:GetObject", "Resource": "arn:aws:s3:::${BUCKET}/*",
  "Condition": { "StringEquals": { "AWS:SourceArn": "arn:aws:cloudfront::${ACCOUNT}:distribution/${DIST_ID}" } }
}]}
JSON
  aws s3api put-bucket-policy --bucket "$BUCKET" --policy file:///tmp/bucket-policy.json
else
  echo "==> Distribution exists ($DIST_ID) — invalidating cache"
  aws cloudfront create-invalidation --distribution-id "$DIST_ID" --paths "/*" >/dev/null
fi

DOMAIN=$(aws cloudfront get-distribution --id "$DIST_ID" --query 'Distribution.DomainName' --output text)
echo ""
echo "==> Done. CloudFront URL (deploys in ~5-15 min the first time):"
echo "    https://${DOMAIN}"
echo "    Backend CORS already allows *.cloudfront.net."
