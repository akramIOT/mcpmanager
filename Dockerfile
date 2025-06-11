FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    docker.io \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml .
COPY src/ src/

# Install Python dependencies
RUN pip install -e .

# Create non-root user
RUN useradd -m -u 1000 mcpmanager && \
    chown -R mcpmanager:mcpmanager /app

USER mcpmanager

# Expose API port
EXPOSE 8000

# Default command
CMD ["mcpm", "serve", "--host", "0.0.0.0", "--port", "8000"]