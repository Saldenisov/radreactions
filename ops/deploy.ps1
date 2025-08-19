# OCR Validator App Deployment Script for Windows
# Run this script to build and deploy the Docker container

Write-Host "🚀 Starting OCR Validator App deployment..." -ForegroundColor Green

# Check if Docker is running
try {
    docker version | Out-Null
    Write-Host "✅ Docker is running" -ForegroundColor Green
} catch {
    Write-Host "❌ Docker is not running. Please start Docker Desktop and try again." -ForegroundColor Red
    exit 1
}

# Build the Docker image
Write-Host "🔨 Building Docker image..." -ForegroundColor Yellow
docker build -t ocr-validator-app .

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Docker image built successfully" -ForegroundColor Green
} else {
    Write-Host "❌ Failed to build Docker image" -ForegroundColor Red
    exit 1
}

# Stop existing container if running
Write-Host "🛑 Stopping existing container (if any)..." -ForegroundColor Yellow
docker-compose down 2>$null

# Start the application
Write-Host "🚀 Starting the application..." -ForegroundColor Yellow
docker-compose up -d

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Application started successfully!" -ForegroundColor Green
    Write-Host "🌐 Access your app at: http://localhost:8501" -ForegroundColor Cyan
    Write-Host "📊 Check container status with: docker-compose ps" -ForegroundColor Blue
    Write-Host "📋 View logs with: docker-compose logs -f" -ForegroundColor Blue
    Write-Host "🛑 Stop the app with: docker-compose down" -ForegroundColor Blue
} else {
    Write-Host "❌ Failed to start the application" -ForegroundColor Red
    Write-Host "📋 Check logs with: docker-compose logs" -ForegroundColor Yellow
    exit 1
}
