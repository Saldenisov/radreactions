# 🌐 Internet Deployment Guide for OCR Validator App

## ⚡ Quick Options (Recommended)

### 1. **Railway** (Easiest & Affordable)
**Cost**: ~$5/month | **Setup**: 5 minutes | **LaTeX**: ✅

1. Go to [railway.app](https://railway.app)
2. Connect your GitHub account
3. Create a new project from your GitHub repo
4. Railway auto-detects Dockerfile
5. Set environment variables:
   - `BASE_DIR=/app/data`
   - `PORT=8501`
6. Deploy automatically!

**Pros**: Easy, affordable, Docker support, automatic HTTPS
**Cons**: No persistent storage (data resets on restart)

### 2. **Render** (Free Tier Available)
**Cost**: Free/$7/month | **Setup**: 10 minutes | **LaTeX**: ✅

1. Go to [render.com](https://render.com)
2. Connect GitHub repo
3. Choose "Web Service"
4. Set build command: `docker build -t app .`
5. Set start command: `docker run -p 10000:8501 app`

### 3. **Google Cloud Run** (Serverless)
**Cost**: Pay per use (~$5-20/month) | **Setup**: 15 minutes | **LaTeX**: ✅

```bash
# Install Google Cloud CLI first
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# Deploy (run from app directory)
chmod +x deploy-gcp.sh
./deploy-gcp.sh
```

## 🏢 Professional Options

### 4. **AWS ECS Fargate**
**Cost**: ~$15-30/month | **Setup**: 30 minutes | **LaTeX**: ✅

1. **Push to ECR**:
```bash
# Create ECR repository
aws ecr create-repository --repository-name ocr-validator-app

# Get login token
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin YOUR_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com

# Build and push
docker build -t ocr-validator-app .
docker tag ocr-validator-app:latest YOUR_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/ocr-validator-app:latest
docker push YOUR_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/ocr-validator-app:latest
```

2. **Create ECS Service**:
   - Use provided `aws-ecs-task.json`
   - Create Application Load Balancer
   - Configure security groups (port 8501)

### 5. **Azure Container Instances**
```bash
# Create resource group
az group create --name ocr-validator-rg --location eastus

# Deploy container
az container create \
    --resource-group ocr-validator-rg \
    --name ocr-validator-app \
    --image your-registry/ocr-validator-app:latest \
    --ports 8501 \
    --dns-name-label ocr-validator-unique \
    --environment-variables BASE_DIR=/app/data \
    --cpu 2 --memory 4
```

## 📦 Data Handling for Internet Deployment

### **Your Dataset**: 3,551 images across 5 tables
- **table5**: 25 images
- **table6**: 1,527 images  
- **table7**: 578 images
- **table8**: 1,284 images
- **table9**: 137 images

### **Full Dataset Deployment** (Recommended)

Use `prepare-full-data.ps1` to include ALL your data in the Docker image:

```powershell
# Prepare all 3,551 images for deployment
.\prepare-full-data.ps1
```

**Pros**:
- ✅ Complete dataset available
- ✅ No external dependencies
- ✅ Downloadable validation databases
- ✅ Self-contained deployment

**Cons**:
- ⚠️ Large Docker image (~500MB-2GB)
- ⚠️ Longer build/deployment times
- ⚠️ Platform size limits may apply

### **Alternative: Cloud Storage**
```python
# For very large deployments, use cloud storage
import boto3

def sync_data_from_s3():
    s3 = boto3.client('s3')
    # Download data on container startup
    pass
```

### **Download Features**
Your deployed app includes:
- **Individual table downloads**: `table5_validation_db.json`
- **Combined download**: `all_tables_validation_data.json`
- **Real-time statistics**: Progress tracking per table

## 🔧 Step-by-Step: Railway Deployment (Recommended)

### 1. Prepare Repository
```bash
# Initialize git repository
git init
git add .
git commit -m "Initial commit"

# Push to GitHub
gh repo create ocr-validator-app --public
git remote add origin https://github.com/YOUR_USERNAME/ocr-validator-app.git
git push -u origin main
```

### 2. Deploy on Railway
1. Visit [railway.app](https://railway.app)
2. Click "Start a New Project"
3. Choose "Deploy from GitHub repo"
4. Select your `ocr-validator-app` repository
5. Railway detects Dockerfile automatically
6. Set environment variables:
   - `BASE_DIR`: `/app/data`
   - `PORT`: `8501`
7. Click "Deploy"

### 3. Configure Custom Domain (Optional)
1. In Railway dashboard, go to Settings
2. Add custom domain: `ocr-validator.yourdomain.com`
3. Update DNS records as instructed

## 🔐 Security Considerations

### Add Basic Authentication
Create `auth.py`:
```python
import streamlit as st
import hashlib

def check_password():
    def password_entered():
        if hashlib.sha256(st.session_state["password"].encode()).hexdigest() == "YOUR_HASH":
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("Password", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("Password", type="password", on_change=password_entered, key="password")
        st.error("Password incorrect")
        return False
    else:
        return True
```

Add to `app.py`:
```python
from auth import check_password
if not check_password():
    st.stop()
```

## 💰 Cost Comparison

| Platform | Free Tier | Paid | LaTeX | Storage | Setup |
|----------|-----------|------|-------|---------|-------|
| Railway | No | $5/month | ✅ | Temporary | Easy |
| Render | 750 hours/month | $7/month | ✅ | Temporary | Easy |
| Google Cloud Run | Yes (limited) | Pay-per-use | ✅ | Temporary | Medium |
| AWS ECS | No | $15-30/month | ✅ | Persistent | Hard |
| Azure | Yes (limited) | $10-25/month | ✅ | Persistent | Medium |

## 🚀 Quick Start Commands

### Railway (Recommended)
```bash
# Install Railway CLI
npm install -g @railway/cli

# Login and deploy
railway login
railway link
railway up
```

### Docker Hub + Any Platform
```bash
# Build and push to Docker Hub
docker build -t your-username/ocr-validator-app .
docker push your-username/ocr-validator-app

# Deploy anywhere using: your-username/ocr-validator-app
```

## 🎯 Next Steps

1. **Choose a platform** (Railway recommended for simplicity)
2. **Push your code to GitHub**
3. **Deploy using the platform's interface**
4. **Configure environment variables**
5. **Test your deployment**
6. **Share the URL with colleagues**

Your app will be accessible worldwide with a URL like:
- `https://your-app-name.railway.app`
- `https://ocr-validator-xxxx.onrender.com`
- `https://your-service-url.run.app`

**Need help?** Each platform has excellent documentation and support!
