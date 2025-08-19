# GitHub Repository Setup Script
param(
    [Parameter(Mandatory=$true)]
    [string]$RepoName = "ocr-validator-app",
    
    [Parameter(Mandatory=$false)]
    [string]$Description = "OCR Validator App with LaTeX support for scientific tables"
)

Write-Host "🚀 Setting up GitHub repository for internet deployment..." -ForegroundColor Green

# Check if GitHub CLI is installed
try {
    gh --version | Out-Null
    Write-Host "✅ GitHub CLI is installed" -ForegroundColor Green
} catch {
    Write-Host "❌ GitHub CLI not found. Please install from: https://cli.github.com/" -ForegroundColor Red
    Write-Host "   Or create repository manually on GitHub" -ForegroundColor Yellow
    exit 1
}

# Check if user is logged in
try {
    gh auth status | Out-Null
    Write-Host "✅ GitHub authentication verified" -ForegroundColor Green
} catch {
    Write-Host "🔐 Please login to GitHub..." -ForegroundColor Yellow
    gh auth login
}

# Initialize git if not already done
if (-not (Test-Path ".git")) {
    Write-Host "📝 Initializing Git repository..." -ForegroundColor Yellow
    git init
    git branch -M main
}

# Create .gitignore if it doesn't exist
if (-not (Test-Path ".gitignore")) {
    Write-Host "📝 Creating .gitignore..." -ForegroundColor Yellow
    @"
# Python
__pycache__/
*.py[cod]
*$py.class
*.so

# Virtual environments
venv/
ENV/
env/

# IDE
.vscode/
.idea/

# OS
.DS_Store
Thumbs.db

# Logs
*.log

# Note: We're including data-full/ in the repository for internet deployment
# This will make the repository large but enables self-contained deployment

# Exclude original source data
E:\ICP_notebooks\Buxton/

# Exclude sample data if using full data
data-sample/

# Docker
.dockerignore

# Environment variables
.env
"@ | Out-File -FilePath ".gitignore" -Encoding utf8
}

# Add all files
Write-Host "📦 Adding files to repository..." -ForegroundColor Yellow
git add .
git commit -m "Initial commit - OCR Validator App with Docker support"

# Create GitHub repository
Write-Host "🌐 Creating GitHub repository..." -ForegroundColor Yellow
try {
    gh repo create $RepoName --public --description $Description --source=. --remote=origin --push
    Write-Host "✅ Repository created successfully!" -ForegroundColor Green
    
    $repoUrl = "https://github.com/$(gh api user --jq .login)/$RepoName"
    Write-Host "🔗 Repository URL: $repoUrl" -ForegroundColor Cyan
    
    Write-Host "`n🚀 Next steps for internet deployment:" -ForegroundColor Green
    Write-Host "1. Choose a platform:" -ForegroundColor White
    Write-Host "   • Railway.app (recommended): $repoUrl -> Deploy" -ForegroundColor Blue
    Write-Host "   • Render.com: $repoUrl -> New Web Service" -ForegroundColor Blue
    Write-Host "   • Google Cloud Run: Use deploy-gcp.sh script" -ForegroundColor Blue
    Write-Host "`n2. Set environment variables:" -ForegroundColor White
    Write-Host "   • BASE_DIR=/app/data" -ForegroundColor Blue
    Write-Host "   • PORT=8501" -ForegroundColor Blue
    Write-Host "`n3. Your app will be live at a URL like:" -ForegroundColor White
    Write-Host "   • https://your-app.railway.app" -ForegroundColor Cyan
    Write-Host "   • https://your-app.onrender.com" -ForegroundColor Cyan
    
} catch {
    Write-Host "❌ Error creating repository: $_" -ForegroundColor Red
    Write-Host "💡 You can create it manually at: https://github.com/new" -ForegroundColor Yellow
}

Write-Host "`n📖 See INTERNET-DEPLOYMENT.md for detailed instructions!" -ForegroundColor Green
