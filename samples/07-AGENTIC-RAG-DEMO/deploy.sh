#!/bin/bash

# Build and deploy the Docker container for the Chainlit Cardiology Assistant

# Step 1: Build the Docker image
echo "Building Docker image..."
docker-compose build

# Step 2: Start the Docker container
echo "Starting Docker container..."
docker-compose up -d

# Step 3: Check if container is running
echo "Checking container status..."
docker-compose ps

echo ""
echo "Deployment completed! Your Chainlit app should be available at http://localhost:8000"
echo "To view logs: docker-compose logs -f"
echo "To stop the service: docker-compose down"