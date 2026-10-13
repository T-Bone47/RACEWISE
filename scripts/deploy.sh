#!/bin/bash
set -e

echo "Deploying PS PKG Aggregator..."

if [ ! -f .env.production ]; then
    echo "Error: .env.production not found"
    exit 1
fi

cp .env.production .env

echo "Building and starting production containers..."
cd infrastructure
docker-compose -f docker-compose.prod.yml pull
docker-compose -f docker-compose.prod.yml up -d --build

echo "Running database migrations..."
docker-compose -f docker-compose.prod.yml exec backend node -e "require('./config/database').initializeDatabase().then(() => console.log('DB initialized')).catch(console.error)"

echo "Deployment complete!"
echo "Application available at: ${FRONTEND_URL}"