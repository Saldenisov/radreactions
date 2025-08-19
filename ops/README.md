# 🔍 OCR Validator App

A Streamlit application for validating and correcting OCR results from scientific table images with full LaTeX support.

## ✨ Features

- 🖼️ Browse and validate table images
- 📝 Edit TSV data with visual tab indicators
- 📄 Generate LaTeX documents and compile to PDF in real-time
- 📊 Track validation progress across multiple tables
- 🧪 Support for scientific notation and chemical formulas
- 🔄 Automatic OCR error correction

## 🚀 Quick Start with Docker (Recommended)

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- Your data directory structure set up (see below)

### Windows Deployment
```powershell
# Run the deployment script
.\deploy.ps1
```

### Linux/Mac Deployment
```bash
# Make script executable and run
chmod +x deploy.sh
./deploy.sh
```

### Manual Docker Commands
```bash
# Build the image
docker build -t ocr-validator-app .

# Run with docker-compose
docker-compose up -d

# Access at http://localhost:8501
```

## 📁 Required Directory Structure

Ensure your data follows this structure:
```
E:/ICP_notebooks/Buxton/  (or your BASE_DIR)
├── table5/
│   └── sub_tables_images/
│       ├── *.png (image files)
│       ├── csv/ (TSV files)
│       │   └── latex/ (generated PDFs)
│       └── validation_db.json
├── table6/
├── table7/
├── table8/
└── table9/
```

## ⚙️ Configuration

### Docker Environment Variables
- `BASE_DIR`: Path to your data directory (default: `/app/data`)

### Volume Mounting
Update the `docker-compose.yml` file to point to your data directory:
```yaml
volumes:
  - "YOUR_DATA_PATH:/app/data"
```

## 🛠️ Local Development (without Docker)

### Prerequisites
- Python 3.11+
- XeLaTeX/MiKTeX installed

### Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run app.py
```

## 📋 Management Commands

```bash
# View running containers
docker-compose ps

# View logs
docker-compose logs -f

# Stop the application
docker-compose down

# Rebuild after changes
docker-compose up --build -d
```

## 🌐 Sharing with Colleagues

### Option 1: Local Network Access
1. Deploy on your machine using Docker
2. Find your IP address: `ipconfig` (Windows) or `ifconfig` (Linux/Mac)
3. Share the URL: `http://YOUR_IP:8501`
4. Ensure firewall allows port 8501

### Option 2: Server Deployment
1. Copy the entire app folder to your server
2. Update the data path in `docker-compose.yml`
3. Run `docker-compose up -d`
4. Access via server's IP or domain

### Option 3: Cloud Deployment
- AWS ECS/EC2
- Google Cloud Run
- Azure Container Instances

## 🐛 Troubleshooting

### Common Issues

**Container won't start:**
```bash
docker-compose logs
```

**Data not loading:**
- Check volume mount path in `docker-compose.yml`
- Verify data directory structure
- Check file permissions

**LaTeX errors:**
- LaTeX packages are included in Docker image
- Check logs for specific LaTeX compilation errors

**Port conflicts:**
```bash
# Use different port
docker-compose down
# Edit docker-compose.yml to change "8501:8501" to "8502:8501"
docker-compose up -d
```

## 🔒 Security Notes

- The app runs on port 8501 by default
- No authentication is built-in - implement reverse proxy with auth if needed
- Data is mounted as volumes - ensure proper file permissions

## 📦 Dependencies

### Python Packages
- Streamlit
- Pillow (PIL)
- PyMuPDF

### System Dependencies (included in Docker)
- TeX Live XeLaTeX
- LaTeX packages for scientific documents
- Font packages for proper rendering
