# Deployment Guide

## Prerequisites

- Docker 24+
- Docker Compose 2+
- Domain name with DNS configured
- SSL certificates (Let's Encrypt recommended)

## Environment Variables

Create `.env.production` with:

```env
# Database
DB_HOST=postgres
DB_PORT=5432
DB_NAME=pspkg
DB_USER=your_secure_user
DB_PASSWORD=your_secure_password

# Redis
REDIS_URL=redis://redis:6379

# Backend
PORT=3001
NODE_ENV=production
FRONTEND_URL=https://yourdomain.com

# Frontend
NEXT_PUBLIC_API_URL=https://yourdomain.com/api

# Scraping
SCRAPE_INTERVAL_HOURS=24
MAX_SCRAPE_PAGES=10
```

## SSL Certificates

Place certificates in `infrastructure/nginx/ssl/`:

```
infrastructure/nginx/ssl/
├── cert.pem
└── key.pem
```

Update `nginx.conf` for HTTPS:

```nginx
server {
    listen 443 ssl http2;
    server_name yourdomain.com;
    
    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;
    
    # ... rest of config
}

server {
    listen 80;
    server_name yourdomain.com;
    return 301 https://$server_name$request_uri;
}
```

## Deploy

```bash
# Copy production env
cp .env.production .env

# Deploy
./scripts/deploy.sh
```

## Manual Deploy Steps

```bash
cd infrastructure

# Pull latest images
docker-compose -f docker-compose.prod.yml pull

# Build and start
docker-compose -f docker-compose.prod.yml up -d --build

# Run migrations
docker-compose -f docker-compose.prod.yml exec backend node -e "require('./config/database').initializeDatabase()"

# Check logs
docker-compose -f docker-compose.prod.yml logs -f
```

## Database Migrations

The `initializeDatabase()` function creates tables automatically. For schema changes:

1. Create migration SQL file in `backend/migrations/`
2. Run manually or add to deployment script

## Backup Strategy

### Database Backup

```bash
# Daily backup via cron
0 2 * * * docker exec pspkg-postgres pg_dump -U postgres pspkg | gzip > /backups/pspkg-$(date +\%F).sql.gz
```

### Restore

```bash
gunzip -c /backups/pspkg-2024-01-15.sql.gz | docker exec -i pspkg-postgres psql -U postgres pspkg
```

## Monitoring

### Health Checks

- Frontend: `https://yourdomain.com/`
- Backend: `https://yourdomain.com/api/health`
- Database: `docker exec pspkg-postgres pg_isready`
- Redis: `docker exec pspkg-redis redis-cli ping`

### Logs

```bash
# View all logs
docker-compose -f docker-compose.prod.yml logs -f

# View specific service
docker-compose -f docker-compose.prod.yml logs -f backend
```

## Scaling

### Horizontal Scaling

```yaml
# In docker-compose.prod.yml
services:
  backend:
    deploy:
      replicas: 3
  frontend:
    deploy:
      replicas: 2
```

Use a load balancer (nginx upstream) for multiple instances.

## Updates

```bash
# Pull latest code
git pull

# Rebuild and deploy
./scripts/deploy.sh
```

## Rollback

```bash
# Tag releases
docker tag pspkg-backend:latest pspkg-backend:v1.0.0

# Rollback
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml up -d --build
# Specify image tag in docker-compose or use docker service update
```