# Sample Data Preparation Script for Internet Deployment
param(
    [Parameter(Mandatory=$false)]
    [int]$SampleSize = 10  # Number of images per table to include
)

Write-Host "📦 Preparing sample data for internet deployment..." -ForegroundColor Green

$sourceBase = "E:\ICP_notebooks\Buxton"
$targetBase = ".\data-sample"

# Create sample data directory
if (Test-Path $targetBase) {
    Remove-Item $targetBase -Recurse -Force
}
New-Item -ItemType Directory -Path $targetBase | Out-Null

$tables = @("table5", "table6", "table7", "table8", "table9")
$totalCopied = 0

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
    
    # Get sample images
    $images = Get-ChildItem "$sourceTable\*.png" | Select-Object -First $SampleSize
    
    foreach ($image in $images) {
        # Copy image
        Copy-Item $image.FullName "$targetTable\"
        
        # Copy corresponding CSV file
        $csvFile = Join-Path "$sourceTable\csv" ($image.BaseName + ".csv")
        if (Test-Path $csvFile) {
            Copy-Item $csvFile "$targetTable\csv\"
        }
        
        # Copy corresponding PDF file
        $pdfFile = Join-Path "$sourceTable\csv\latex" ($image.BaseName + ".pdf")
        if (Test-Path $pdfFile) {
            Copy-Item $pdfFile "$targetTable\csv\latex\"
        }
        
        $totalCopied++
    }
    
    # Create empty validation database
    $validationDb = @{}
    foreach ($image in $images) {
        $validationDb[$image.Name] = $false
    }
    
    $dbPath = Join-Path $targetTable "validation_db.json"
    $validationDb | ConvertTo-Json -Depth 2 | Out-File $dbPath -Encoding utf8
    
    Write-Host "  ✅ Copied $($images.Count) images from $table" -ForegroundColor Green
}

Write-Host "📊 Total sample images: $totalCopied" -ForegroundColor Cyan

# Update Dockerfile to include sample data
$dockerfileContent = Get-Content "Dockerfile" -Raw
if ($dockerfileContent -notmatch "COPY data-sample") {
    Write-Host "📝 Updating Dockerfile to include sample data..." -ForegroundColor Yellow
    
    $newDockerfile = $dockerfileContent -replace 
        '# Create data directory for mounting\r\nRUN mkdir -p /app/data',
        "# Copy sample data for internet deployment`r`nCOPY data-sample/ /app/data/`r`n`r`n# Create data directory for mounting`r`nRUN mkdir -p /app/data-mount"
    
    $newDockerfile | Out-File "Dockerfile" -Encoding utf8 -NoNewline
    Write-Host "✅ Dockerfile updated" -ForegroundColor Green
}

# Create environment-specific config
@"
import os
from pathlib import Path

AVAILABLE_TABLES = ['table5', 'table6', 'table7', 'table8', 'table9']

# Use environment variable for deployment, fallback to sample data for internet deployment
if os.getenv('DEPLOYMENT_TYPE') == 'internet':
    BASE_DIR = Path('/app/data')  # Sample data embedded in container
else:
    BASE_DIR = Path(os.getenv('BASE_DIR', r"E:\ICP_notebooks\Buxton"))

def get_table_paths(table_choice):
    image_dir = BASE_DIR / table_choice / "sub_tables_images"
    pdf_dir = image_dir / "csv" / "latex"
    tsv_dir = image_dir / "csv"
    db_path = image_dir / "validation_db.json"
    return image_dir, pdf_dir, tsv_dir, db_path
"@ | Out-File "config.py" -Encoding utf8

Write-Host "✅ Sample data preparation complete!" -ForegroundColor Green
Write-Host "📁 Sample data location: $targetBase" -ForegroundColor Blue
Write-Host "📊 Ready for internet deployment with $totalCopied sample images" -ForegroundColor Cyan
Write-Host "`n🚀 Next steps:" -ForegroundColor Green
Write-Host "1. Run: .\setup-github.ps1" -ForegroundColor Blue
Write-Host "2. Deploy on Railway/Render with sample data" -ForegroundColor Blue
Write-Host "3. For production: mount full data as volumes" -ForegroundColor Blue
