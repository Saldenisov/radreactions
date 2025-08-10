# 🚀 OCR Validator App - Deployment Guide

## ✅ Your Setup is Complete!

Your OCR Validator App is now ready for Docker deployment with:
- **3,551 total images** across 5 tables
- **Full LaTeX support** for PDF generation
- **Easy sharing** with colleagues

## 🎯 Quick Deployment

### For Windows:
```powershell
# Run setup check (optional)
.\check-setup.ps1

# Deploy the application
.\deploy.ps1
```

### For Linux/Mac:
```bash
# Make scripts executable
chmod +x *.sh

# Deploy the application  
./deploy.sh
```

### Manual Commands:
```bash
docker-compose up -d
```

## 🌐 Accessing the Application

Once deployed, access your app at:
- **Local**: http://localhost:8501
- **Network**: http://YOUR_IP_ADDRESS:8501

## 📊 Your Data Summary

- ✅ **table5**: 25 images
- ✅ **table6**: 1,527 images  
- ✅ **table7**: 578 images
- ✅ **table8**: 1,284 images
- ✅ **table9**: 137 images

**Total**: 3,551 images ready for validation

## 🤝 Sharing with Colleagues

### Option 1: Same Network
1. Deploy on your machine
2. Find your IP: `ipconfig`
3. Share: `http://YOUR_IP:8501`
4. Ensure Windows Firewall allows port 8501

### Option 2: Server Deployment  
1. Copy app folder to server
2. Update data path in `docker-compose.yml`
3. Run `docker-compose up -d`

### Option 3: Cloud Server
Deploy on AWS, Azure, or Google Cloud with Docker support

## 🛠️ Management Commands

```bash
# Check status
docker-compose ps

# View logs
docker-compose logs -f

# Stop application
docker-compose down

# Rebuild after changes
docker-compose up --build -d

# Update and restart
docker-compose pull
docker-compose up -d
```

## 🔧 Configuration

### Change Port (if 8501 is busy):
Edit `docker-compose.yml`:
```yaml
ports:
  - "8502:8501"  # Use port 8502 instead
```

### Different Data Path:
Edit `docker-compose.yml`:
```yaml
volumes:
  - "/your/data/path:/app/data"
```

## 🐛 Troubleshooting

### Common Issues:

**Port already in use:**
```bash
docker-compose down
# Edit docker-compose.yml to change port
docker-compose up -d
```

**Permission denied:**
```bash
# On Windows
Get-Acl E:\ICP_notebooks\Buxton | Set-Acl

# On Linux
sudo chown -R $USER:$USER /path/to/data
```

**Container won't start:**
```bash
docker-compose logs ocr-validator
```

### LaTeX Issues:
- All LaTeX packages are included in Docker image
- Check container logs for specific compilation errors
- Ensure TSV data is properly formatted

## 🎉 You're Ready to Go!

Your OCR Validator App is production-ready with:
- ✅ Full Docker containerization
- ✅ LaTeX support for PDF generation  
- ✅ All dependencies included
- ✅ Easy deployment scripts
- ✅ Comprehensive documentation

**Next Steps:**
1. Run `.\deploy.ps1`
2. Open http://localhost:8501
3. Start validating your 3,551 images!
4. Share with colleagues using your IP address

---

**Need Help?** Check the logs with `docker-compose logs -f`
