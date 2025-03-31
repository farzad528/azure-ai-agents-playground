# PowerShell script for deploying Chainlit app to Azure using azd

Write-Host "Starting deployment of Chainlit Cardio Assistant to Azure..." -ForegroundColor Green

# Check if azd is installed
try {
    $azdVersion = azd version
    Write-Host "Azure Developer CLI version: $azdVersion" -ForegroundColor Green
}
catch {
    Write-Host "Azure Developer CLI (azd) is not installed. Please install it first." -ForegroundColor Red
    Write-Host "You can install it using: winget install Microsoft.Azd" -ForegroundColor Yellow
    exit 1
}

# Check if Docker is running
try {
    $dockerStatus = docker info
    Write-Host "Docker is running properly." -ForegroundColor Green
}
catch {
    Write-Host "Docker doesn't seem to be running. Please start Docker Desktop." -ForegroundColor Red
    exit 1
}

# Login to Azure
Write-Host "Logging in to Azure..." -ForegroundColor Green
azd auth login

# Initialize the azd environment if not already done
if (-not (Test-Path "./.azure")) {
    Write-Host "Initializing azd environment..." -ForegroundColor Green
    azd init
}

# Deploy the application
Write-Host "Deploying the application..." -ForegroundColor Green
azd up

Write-Host "Deployment completed. Your app should be available at the URL shown above." -ForegroundColor Green