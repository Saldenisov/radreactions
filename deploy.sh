#!/bin/bash
# OCR Validator App Deployment Script for Linux/Mac
# Run this script to build and deploy the Docker container

echo "🚀 Starting OCR Validator App deployment..."

# Check if Docker is running
if ! docker version > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker and try again."
    exit 1
fi
echo "✅ Docker is running"

# Build the Docker image
echo "🔨 Building Docker image..."
if docker build -t ocr-validator-app .; then
    echo "✅ Docker image built successfully"
else
    echo "❌ Failed to build Docker image"
    exit 1
fi

# Stop existing container if running
echo "🛑 Stopping existing container (if any)..."
docker-compose down 2>/dev/null || true

# Start the application
echo "🚀 Starting the application..."
if docker-compose up -d; then
    echo "✅ Application started successfully!"
    echo "🌐 Access your app at: http://localhost:8501"
    echo "📊 Check container status with: docker-compose ps"
    echo "📋 View logs with: docker-compose logs -f"
    echo "🛑 Stop the app with: docker-compose down"
else
    echo "❌ Failed to start the application"
    echo "📋 Check logs with: docker-compose logs"
    exit 1
fi
