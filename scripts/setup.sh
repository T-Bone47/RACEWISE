#!/bin/bash
set -e

echo "Setting up PS PKG Aggregator..."

if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env from .env.example - please update with your values"
fi

echo "Installing frontend dependencies..."
cd frontend && npm install

echo "Installing backend dependencies..."
cd ../backend && npm install

echo "Starting infrastructure..."
cd ../infrastructure && docker-compose up -d

echo "Waiting for database to be ready..."
sleep 10

echo "Initializing database..."
cd ../backend && npm run init-db 2>/dev/null || node -e "require('./config/database').initializeDatabase().then(() => console.log('DB initialized')).catch(console.error)"

echo ""
echo "Setup complete! Start development servers with:"
echo "  Frontend: cd frontend && npm run dev"
echo "  Backend:  cd backend && npm run dev"
echo ""
echo "Or run everything with Docker:"
echo "  cd infrastructure && docker-compose up"