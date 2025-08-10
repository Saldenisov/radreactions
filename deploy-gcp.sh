#!/bin/bash
# Google Cloud Run deployment script

PROJECT_ID="your-project-id"
SERVICE_NAME="ocr-validator-app"
REGION="us-central1"

echo "🚀 Deploying to Google Cloud Run..."

# Build and push to Container Registry
echo "📦 Building and pushing Docker image..."
gcloud builds submit --tag gcr.io/$PROJECT_ID/$SERVICE_NAME

# Deploy to Cloud Run
echo "🌐 Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
    --image gcr.io/$PROJECT_ID/$SERVICE_NAME \
    --platform managed \
    --region $REGION \
    --allow-unauthenticated \
    --port 8501 \
    --memory 2Gi \
    --cpu 1 \
    --set-env-vars BASE_DIR=/app/data \
    --set-env-vars STREAMLIT_SERVER_HEADLESS=true

echo "✅ Deployment complete!"
echo "🌐 Your app URL:"
gcloud run services describe $SERVICE_NAME --platform managed --region $REGION --format 'value(status.url)'
