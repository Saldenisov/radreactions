# Full Data Preparation Script for Internet Deployment
# This script prepares ALL your data (3,551 images) for internet deployment

param(
    [Parameter(Mandatory=$false)]
    [switch]$CompressImages = $true,  # Compress images to reduce Docker image size
    [Parameter(Mandatory=$false)]
    [int]$ImageQuality = 85          # JPEG quality for compression
)

Write-Host "📦 Preparing FULL data (3,551 images) for internet deployment..." -ForegroundColor Green

$sourceBase = "E:\ICP_notebooks\Buxton"
$targetBase = ".\data-full"

# Create full data directory
if (Test-Path $targetBase) {
    Write-Host "🗑️ Removing existing data directory..." -ForegroundColor Yellow
    Remove-Item $targetBase -Recurse -Force
}
New-Item -ItemType Directory -Path $targetBase | Out-Null

$tables = @("table5", "table6", "table7", "table8", "table9")
$totalCopied = 0
$totalSize = 0

foreach ($table in $tables) {
    Write-Host "Processing $table..." -ForegroundColor Yellow
    
    $sourceTable = Join-Path $sourceBase "$table\sub_tables_images"
    $targetTable = Join-Path $targetBase "$table\sub_tables_images"
    
    if (-not (Test-Path $sourceTable)) {
        Write-Host "  ⚠️ Source table not found: $sourceTable" -ForegroundColor Yellow
        continue
    }
    
    # Create target directory structure
    New-Item -ItemType Directory -Path $targetTable -Force | Out-Null
    New-Item -ItemType Directory -Path "$targetTable\csv" -Force | Out-Null
    New-Item -ItemType Directory -Path "$targetTable\csv\latex" -Force | Out-Null
    
    # Get all images
    $images = Get-ChildItem "$sourceTable\*.png"
    Write-Host "  Found $($images.Count) images in $table" -ForegroundColor Cyan
    
    foreach ($image in $images) {
        # Copy image (with optional compression)
        if ($CompressImages) {
            # Note: PowerShell doesn't have built-in image compression
            # For now, just copy the original files
            # In production, you might want to use ImageMagick or similar
            Copy-Item $image.FullName "$targetTable\"
        } else {
            Copy-Item $image.FullName "$targetTable\"
        }
        
        # Copy corresponding CSV file
        $csvFile = Join-Path "$sourceTable\csv" ($image.BaseName + ".csv")
        if (Test-Path $csvFile) {
            Copy-Item $csvFile "$targetTable\csv\"
        } else {
            Write-Host "    ⚠️ CSV file not found for: $($image.Name)" -ForegroundColor Yellow
        }
        
        # Copy corresponding PDF file
        $pdfFile = Join-Path "$sourceTable\csv\latex" ($image.BaseName + ".pdf")
        if (Test-Path $pdfFile) {
            Copy-Item $pdfFile "$targetTable\csv\latex\"
        }
        
        $totalCopied++
        $totalSize += $image.Length
        
        # Show progress every 100 files
        if ($totalCopied % 100 -eq 0) {
            Write-Host "    📊 Progress: $totalCopied images copied" -ForegroundColor Blue
        }
    }
    
    # Copy existing validation database or create new one
    $sourceValidationDb = Join-Path $sourceTable "validation_db.json"
    $targetValidationDb = Join-Path $targetTable "validation_db.json"
    
    if (Test-Path $sourceValidationDb) {
        Copy-Item $sourceValidationDb $targetValidationDb
        Write-Host "  ✅ Copied existing validation database" -ForegroundColor Green
    } else {
        # Create empty validation database
        $validationDb = @{}
        foreach ($image in $images) {
            $validationDb[$image.Name] = $false
        }
        
        $validationDb | ConvertTo-Json -Depth 2 | Out-File $targetValidationDb -Encoding utf8
        Write-Host "  ✅ Created new validation database" -ForegroundColor Green
    }
    
    Write-Host "  ✅ Completed $table with $($images.Count) images" -ForegroundColor Green
}

$totalSizeMB = [math]::Round($totalSize / 1MB, 2)
Write-Host "`n📊 Full Data Preparation Summary:" -ForegroundColor Green
Write-Host "  • Total images: $totalCopied" -ForegroundColor Cyan
Write-Host "  • Total size: ${totalSizeMB} MB" -ForegroundColor Cyan
Write-Host "  • Data location: $targetBase" -ForegroundColor Cyan

# Update Dockerfile to include full data
Write-Host "`n📝 Updating Dockerfile for full data deployment..." -ForegroundColor Yellow

$dockerfileContent = Get-Content "Dockerfile" -Raw

# Replace any existing data copy with full data
$newDockerfile = $dockerfileContent -replace 
    'COPY data-sample/ /app/data/',
    'COPY data-full/ /app/data/'

# If no data copy exists, add it
if ($newDockerfile -notmatch "COPY data-full") {
    $newDockerfile = $newDockerfile -replace 
        '# Create data directory for mounting\r\nRUN mkdir -p /app/data',
        "# Copy full dataset for internet deployment`r`nCOPY data-full/ /app/data/`r`n`r`n# Create data directory for mounting`r`nRUN mkdir -p /app/data-mount"
}

$newDockerfile | Out-File "Dockerfile" -Encoding utf8 -NoNewline

# Create .dockerignore to exclude unnecessary files
Write-Host "📝 Creating optimized .dockerignore..." -ForegroundColor Yellow
@"
# Python cache
__pycache__/
*.py[cod]
*`$py.class

# Virtual environments
venv/
env/

# IDE files
.vscode/
.idea/
*.swp
*.swo

# OS files
.DS_Store
Thumbs.db

# Git files
.git/
.gitignore

# Documentation (to reduce image size)
*.md
DEPLOYMENT.md
INTERNET-DEPLOYMENT.md

# Scripts (not needed in container)
*.ps1
*.sh
setup-github.ps1
prepare-*.ps1
deploy-*.sh
check-setup.ps1

# Docker files
docker-compose.yml
docker-compose.override.yml
.dockerignore

# Sample data (we're using full data)
data-sample/

# Original source data (we're using copied data-full)
# Note: Don't exclude data-full as it's needed in the container
"@ | Out-File ".dockerignore" -Encoding utf8

Write-Host "`n⚠️ WARNING: Docker image will be LARGE (~${totalSizeMB} MB + system dependencies)" -ForegroundColor Yellow
Write-Host "Consider using cloud storage for production deployments with this much data." -ForegroundColor Yellow

Write-Host "`n✅ Full data preparation complete!" -ForegroundColor Green
Write-Host "📁 Full data location: $targetBase" -ForegroundColor Blue
Write-Host "📊 Ready for internet deployment with ALL $totalCopied images" -ForegroundColor Cyan

Write-Host "`n🚀 Next steps:" -ForegroundColor Green
Write-Host "1. .\setup-github.ps1 - Create GitHub repository" -ForegroundColor Blue
Write-Host "2. Choose deployment platform:" -ForegroundColor Blue
Write-Host "   • Railway: May have size limits, consider upgrading plan" -ForegroundColor Yellow
Write-Host "   • Google Cloud Run: Good for large containers" -ForegroundColor Blue  
Write-Host "   • AWS ECS: Best for production with large datasets" -ForegroundColor Blue
Write-Host "3. Set environment variables:" -ForegroundColor Blue
Write-Host "   • BASE_DIR=/app/data" -ForegroundColor Yellow
Write-Host "   • PORT=8501" -ForegroundColor Yellow

Write-Host "`n💡 Performance Tips:" -ForegroundColor Green
Write-Host "• Large Docker images take longer to build and deploy" -ForegroundColor Yellow
Write-Host "• Consider using cloud storage (S3/GCS) for production" -ForegroundColor Yellow
Write-Host "• Monitor deployment platform size limits" -ForegroundColor Yellow
