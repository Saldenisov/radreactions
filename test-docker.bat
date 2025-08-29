@echo off
echo Building Docker image...
docker build -t radreactions:test -f Dockerfile .

if %ERRORLEVEL% neq 0 (
    echo Build failed!
    exit /b 1
)

echo Build successful! Starting container...
docker run -d --name radreactions-test -p 8501:8501 -e DATA_DIR=/data radreactions:test

if %ERRORLEVEL% neq 0 (
    echo Failed to start container!
    exit /b 1
)

echo Container started! Waiting for startup...
timeout /t 10 /nobreak >nul

echo Checking container logs...
docker logs radreactions-test

echo.
echo Testing health endpoint...
curl -f http://localhost:8501/_stcore/health
if %ERRORLEVEL% equ 0 (
    echo.
    echo SUCCESS! Container is running and healthy.
    echo Access the app at: http://localhost:8501
) else (
    echo.
    echo Health check failed. Check logs above.
)

echo.
echo To stop the test container, run: docker stop radreactions-test
echo To remove the test container, run: docker rm radreactions-test
