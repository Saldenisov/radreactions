# Complete Internet Deployment Script for OCR Validator App
# This script prepares ALL data and sets up GitHub for internet deployment

param(
    [Parameter(Mandatory=$false)]
    [string]$RepoName = "ocr-validator-app",
    [Parameter(Mandatory=$false)]
    [switch]$SkipDataPrep = $false,
    [Parameter(Mandatory=$false)]
    [switch]$SkipGitHub = $false
)

Write-Host "🌐 Complete Internet Deployment Setup" -ForegroundColor Green
Write-Host "=====================================`n" -ForegroundColor Green

# Step 1: Prepare full dataset
if (-not $SkipDataPrep) {
    Write-Host "📦 Step 1: Preparing full dataset (3,551 images)..." -ForegroundColor Yellow

    if (Test-Path ".\prepare-full-data.ps1") {
        .\prepare-full-data.ps1
        if ($LASTEXITCODE -ne 0) {
            Write-Host "❌ Data preparation failed" -ForegroundColor Red
            exit 1
        }
    } else {
        Write-Host "❌ prepare-full-data.ps1 not found" -ForegroundColor Red
        exit 1
    }

    Write-Host "✅ Data preparation complete`n" -ForegroundColor Green
} else {
    Write-Host "⏭️ Skipping data preparation`n" -ForegroundColor Blue
}

# Step 2: Setup GitHub repository
if (-not $SkipGitHub) {
    Write-Host "🐙 Step 2: Setting up GitHub repository..." -ForegroundColor Yellow

    if (Test-Path ".\setup-github.ps1") {
        .\setup-github.ps1 -RepoName $RepoName
        if ($LASTEXITCODE -ne 0) {
            Write-Host "❌ GitHub setup failed" -ForegroundColor Red
            exit 1
        }
    } else {
        Write-Host "❌ setup-github.ps1 not found" -ForegroundColor Red
        exit 1
    }

    Write-Host "✅ GitHub repository setup complete`n" -ForegroundColor Green
} else {
    Write-Host "⏭️ Skipping GitHub setup`n" -ForegroundColor Blue
}

# Step 3: Deployment summary
Write-Host "🎉 Internet Deployment Ready!" -ForegroundColor Green
Write-Host "==============================`n" -ForegroundColor Green

Write-Host "📊 Your Dataset Summary:" -ForegroundColor Cyan
Write-Host "• Total Images: 3,551" -ForegroundColor White
Write-Host "• Tables: table5 (25), table6 (1,527), table7 (578), table8 (1,284), table9 (137)" -ForegroundColor White
Write-Host "• Download Features: Individual & combined validation databases" -ForegroundColor White
Write-Host "• LaTeX Support: Full TeX Live XeLaTeX included`n" -ForegroundColor White

Write-Host "🚀 Next Steps - Choose Your Deployment Platform:" -ForegroundColor Green

Write-Host "`n1️⃣ RAILWAY (Recommended - Easiest)" -ForegroundColor Yellow
Write-Host "   • Cost: ~$5/month" -ForegroundColor White
Write-Host "   • Setup: 5 minutes" -ForegroundColor White
Write-Host "   • Steps:" -ForegroundColor White
Write-Host "     - Go to railway.app" -ForegroundColor Blue
Write-Host "     - Connect GitHub account" -ForegroundColor Blue
Write-Host "     - Select your repository: $RepoName" -ForegroundColor Blue
Write-Host "     - Set: BASE_DIR=/app/data, PORT=8501" -ForegroundColor Blue
Write-Host "     - Deploy!" -ForegroundColor Blue

Write-Host "`n2️⃣ RENDER (Free Option)" -ForegroundColor Yellow
Write-Host "   • Cost: Free (750 hours/month)" -ForegroundColor White
Write-Host "   • Setup: 10 minutes" -ForegroundColor White
Write-Host "   • Steps:" -ForegroundColor White
Write-Host "     - Go to render.com" -ForegroundColor Blue
Write-Host "     - Connect GitHub repo" -ForegroundColor Blue
Write-Host "     - Choose Web Service" -ForegroundColor Blue
Write-Host "     - Auto-detects Dockerfile" -ForegroundColor Blue

Write-Host "`n3️⃣ GOOGLE CLOUD RUN (Serverless)" -ForegroundColor Yellow
Write-Host "   • Cost: Pay-per-use (~$5-20/month)" -ForegroundColor White
Write-Host "   • Setup: 15 minutes" -ForegroundColor White
Write-Host "   • Steps:" -ForegroundColor White
Write-Host "     - Install Google Cloud CLI" -ForegroundColor Blue
Write-Host "     - Run: ./deploy-gcp.sh" -ForegroundColor Blue

Write-Host "`n📱 Your App Features:" -ForegroundColor Green
Write-Host "✅ Browse and validate all 3,551 images" -ForegroundColor White
Write-Host "✅ Edit TSV data with LaTeX compilation" -ForegroundColor White
Write-Host "✅ Download validation databases per table" -ForegroundColor White
Write-Host "✅ Real-time progress tracking" -ForegroundColor White
Write-Host "✅ Automatic OCR error correction" -ForegroundColor White
Write-Host "✅ Global internet access with HTTPS" -ForegroundColor White

Write-Host "`n🔗 Once deployed, colleagues can access at:" -ForegroundColor Green
Write-Host "• https://your-app.railway.app" -ForegroundColor Cyan
Write-Host "• https://your-app.onrender.com" -ForegroundColor Cyan
Write-Host "• https://your-service-url.run.app" -ForegroundColor Cyan

Write-Host "`n📥 Download Features Available:" -ForegroundColor Green
Write-Host "• Individual table DBs: table5_validation_db.json, etc." -ForegroundColor White
Write-Host "• Combined export: all_tables_validation_data.json" -ForegroundColor White
Write-Host "• Includes timestamps and statistics" -ForegroundColor White

Write-Host "`n⚠️ Important Notes:" -ForegroundColor Yellow
Write-Host "• Docker image will be large (~1-2GB) due to full dataset" -ForegroundColor White
Write-Host "• First deployment may take 10-15 minutes" -ForegroundColor White
Write-Host "• Consider upgrading platform plans for better performance" -ForegroundColor White

Write-Host "`n📖 Documentation:" -ForegroundColor Green
Write-Host "• INTERNET-DEPLOYMENT.md - Detailed deployment guide" -ForegroundColor Blue
Write-Host "• README.md - Local development instructions" -ForegroundColor Blue
Write-Host "• DEPLOYMENT.md - Local deployment guide" -ForegroundColor Blue

Write-Host "`n✨ Ready to deploy! Choose your platform and go live! 🌐" -ForegroundColor Green
