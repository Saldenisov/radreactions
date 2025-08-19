# Setup verification script for OCR Validator App
Write-Host "🔍 Checking OCR Validator App setup..." -ForegroundColor Green

# Check Docker
try {
    $dockerVersion = docker --version
    Write-Host "✅ Docker: $dockerVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Docker not found. Please install Docker Desktop." -ForegroundColor Red
    exit 1
}

# Check data directory
$dataPath = "E:\ICP_notebooks\Buxton"
if (Test-Path $dataPath) {
    Write-Host "✅ Data directory found: $dataPath" -ForegroundColor Green
    
    # Check for table directories
    $tables = @("table5", "table6", "table7", "table8", "table9")
    $foundTables = @()
    
    foreach ($table in $tables) {
        $tablePath = Join-Path $dataPath "$table\sub_tables_images"
        if (Test-Path $tablePath) {
            $foundTables += $table
            $imageCount = (Get-ChildItem "$tablePath\*.png" -ErrorAction SilentlyContinue | Measure-Object).Count
            Write-Host "  ✅ $table ($imageCount images)" -ForegroundColor Green
        }
    }
    
    if ($foundTables.Count -eq 0) {
        Write-Host "⚠️ No table directories found with proper structure" -ForegroundColor Yellow
    } else {
        Write-Host "📊 Found $($foundTables.Count) table(s): $($foundTables -join ', ')" -ForegroundColor Cyan
    }
} else {
    Write-Host "⚠️ Data directory not found: $dataPath" -ForegroundColor Yellow
    Write-Host "   Update docker-compose.yml with your correct data path" -ForegroundColor Blue
}

# Check required files
$requiredFiles = @("Dockerfile", "docker-compose.yml", "requirements.txt", "app.py")
foreach ($file in $requiredFiles) {
    if (Test-Path $file) {
        Write-Host "✅ $file" -ForegroundColor Green
    } else {
        Write-Host "❌ $file missing" -ForegroundColor Red
    }
}

Write-Host "`n🚀 Ready to deploy! Run: .\deploy.ps1" -ForegroundColor Cyan
