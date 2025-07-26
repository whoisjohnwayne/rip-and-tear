# Rip and Tear Makefile

.PHONY: help build start stop restart logs clean test setup status

# Default target
help:
	@echo "🎵 Rip and Tear Management"
	@echo "========================="
	@echo ""
	@echo "Available commands:"
	@echo "  setup    - Run initial setup"
	@echo "  build    - Build the Docker image"
	@echo "  start    - Start Rip and Tear"
	@echo "  stop     - Stop Rip and Tear"
	@echo "  restart  - Restart Rip and Tear"
	@echo "  logs     - View logs"
	@echo "  status   - Show container status"
	@echo "  test     - Run component tests"
	@echo "  clean    - Clean up containers and images"
	@echo "  shell    - Open shell in container"
	@echo ""
	@echo "Web interface: http://localhost:8080"

# Run setup script
setup:
	@echo "🔧 Running setup..."
	./setup.sh

# Build Docker image
build:
	@echo "🏗️  Building Docker image..."
	docker-compose build

# Start services
start:
	@echo "🚀 Starting Rip and Tear..."
	docker-compose up -d
	@echo "✅ Rip and Tear started!"
	@echo "🌐 Web interface: http://localhost:8080"

# Stop services
stop:
	@echo "🛑 Stopping Rip and Tear..."
	docker-compose down

# Restart services
restart: stop start

# View logs
logs:
	@echo "📋 Viewing logs (Ctrl+C to exit)..."
	docker-compose logs -f

# Show status
status:
	@echo "📊 Container status:"
	docker-compose ps
	@echo ""
	@echo "📝 Recent logs:"
	docker-compose logs --tail=10

# Run tests
test:
	@echo "🧪 Running component tests..."
	python3 test.py

# Clean up
clean:
	@echo "🧹 Cleaning up..."
	docker-compose down --volumes --remove-orphans
	docker system prune -f
	@echo "✅ Cleanup complete"

# Open shell in container
shell:
	@echo "🐚 Opening shell in Rip and Tear container..."
	docker-compose exec rip-and-tear /bin/bash

# Quick commands
up: start
down: stop
ps: status
