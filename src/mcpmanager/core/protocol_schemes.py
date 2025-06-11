"""Protocol scheme support for package managers."""

import asyncio
import logging
import re
import tempfile
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

from mcpmanager.exceptions import MCPManagerError

logger = logging.getLogger(__name__)


class ProtocolSchemeError(MCPManagerError):
    """Protocol scheme processing error."""
    pass


class ProtocolSchemeHandler(ABC):
    """Abstract base class for protocol scheme handlers."""

    @abstractmethod
    def can_handle(self, scheme: str) -> bool:
        """Check if this handler can process the given scheme."""
        pass

    @abstractmethod
    async def process(self, url: str, build_context: Path) -> Tuple[str, List[str]]:
        """Process the scheme URL and return (dockerfile_content, build_args)."""
        pass

    @abstractmethod
    def get_scheme_name(self) -> str:
        """Get the scheme name this handler supports."""
        pass


class UvxSchemeHandler(ProtocolSchemeHandler):
    """Handler for uvx:// scheme (Python/uv package manager)."""

    def can_handle(self, scheme: str) -> bool:
        """Check if this is a uvx scheme."""
        return scheme == "uvx"

    def get_scheme_name(self) -> str:
        """Get scheme name."""
        return "uvx"

    async def process(self, url: str, build_context: Path) -> Tuple[str, List[str]]:
        """Process uvx:// URL."""
        parsed = urlparse(url)
        package_spec = parsed.netloc + parsed.path
        
        if not package_spec:
            raise ProtocolSchemeError("Invalid uvx URL: missing package specification")

        # Extract package name and version
        if "@" in package_spec:
            package_name, version = package_spec.rsplit("@", 1)
        else:
            package_name = package_spec
            version = "latest"

        dockerfile_content = f"""
FROM python:3.11-slim

# Install uv
RUN pip install uv

# Install the package
RUN uv tool install {package_name}{'@' + version if version != 'latest' else ''}

# Set up environment
ENV PATH="/root/.local/bin:$PATH"

# Default command (will be overridden)
CMD ["{package_name.split('.')[-1]}"]
"""

        return dockerfile_content.strip(), []


class NpxSchemeHandler(ProtocolSchemeHandler):
    """Handler for npx:// scheme (Node.js/npm package manager)."""

    def can_handle(self, scheme: str) -> bool:
        """Check if this is an npx scheme."""
        return scheme == "npx"

    def get_scheme_name(self) -> str:
        """Get scheme name."""
        return "npx"

    async def process(self, url: str, build_context: Path) -> Tuple[str, List[str]]:
        """Process npx:// URL."""
        parsed = urlparse(url)
        package_spec = parsed.netloc + parsed.path
        
        if not package_spec:
            raise ProtocolSchemeError("Invalid npx URL: missing package specification")

        # Extract package name and version
        if "@" in package_spec and not package_spec.startswith("@"):
            # Handle scoped packages like @org/package@version
            parts = package_spec.split("@")
            if len(parts) >= 3:  # @org/package@version
                package_name = "@".join(parts[:-1])
                version = parts[-1]
            else:  # package@version
                package_name, version = parts
        else:
            package_name = package_spec
            version = "latest"

        dockerfile_content = f"""
FROM node:18-slim

# Create app directory
WORKDIR /app

# Install the package globally
RUN npm install -g {package_name}{'@' + version if version != 'latest' else ''}

# Default command (will be overridden)
CMD ["{package_name.split('/')[-1]}"]
"""

        return dockerfile_content.strip(), []


class GoSchemeHandler(ProtocolSchemeHandler):
    """Handler for go:// scheme (Go modules)."""

    def can_handle(self, scheme: str) -> bool:
        """Check if this is a go scheme."""
        return scheme == "go"

    def get_scheme_name(self) -> str:
        """Get scheme name."""
        return "go"

    async def process(self, url: str, build_context: Path) -> Tuple[str, List[str]]:
        """Process go:// URL."""
        parsed = urlparse(url)
        module_path = parsed.netloc + parsed.path
        
        if not module_path:
            raise ProtocolSchemeError("Invalid go URL: missing module specification")

        # Handle local paths
        if module_path.startswith("./") or module_path.startswith("/") or module_path == ".":
            return await self._process_local_go_project(module_path, build_context)
        
        # Handle remote modules
        return await self._process_remote_go_module(module_path)

    async def _process_local_go_project(self, local_path: str, build_context: Path) -> Tuple[str, List[str]]:
        """Process local Go project."""
        # Resolve the local path
        if local_path == ".":
            source_dir = Path.cwd()
        elif local_path.startswith("./"):
            source_dir = Path.cwd() / local_path[2:]
        else:
            source_dir = Path(local_path)

        if not source_dir.exists():
            raise ProtocolSchemeError(f"Local Go project path does not exist: {source_dir}")

        # Copy source code to build context
        source_in_context = build_context / "src"
        shutil.copytree(source_dir, source_in_context, dirs_exist_ok=True)

        # Check for go.mod
        go_mod_path = source_in_context / "go.mod"
        if not go_mod_path.exists():
            raise ProtocolSchemeError(f"No go.mod found in {source_dir}")

        # Read module name from go.mod
        with open(go_mod_path, 'r') as f:
            for line in f:
                if line.startswith("module "):
                    module_name = line.split()[1].strip()
                    break
            else:
                raise ProtocolSchemeError("Could not find module name in go.mod")

        dockerfile_content = f"""
FROM golang:1.21-alpine AS builder

WORKDIR /app
COPY src/ .

# Download dependencies
RUN go mod download

# Build the application
RUN go build -o main .

# Final stage
FROM alpine:latest

RUN apk --no-cache add ca-certificates
WORKDIR /root/

COPY --from=builder /app/main .

CMD ["./main"]
"""

        return dockerfile_content.strip(), []

    async def _process_remote_go_module(self, module_path: str) -> Tuple[str, List[str]]:
        """Process remote Go module."""
        # Extract version if specified
        if "@" in module_path:
            module_name, version = module_path.rsplit("@", 1)
        else:
            module_name = module_path
            version = "latest"

        dockerfile_content = f"""
FROM golang:1.21-alpine AS builder

WORKDIR /app

# Initialize module and install package
RUN go mod init temp && go get {module_name}{'@' + version if version != 'latest' else ''}

# Create a simple main.go that imports and runs the package
RUN echo 'package main\n\nimport "{module_name}"\n\nfunc main() {{\n\t// Package should provide its own main\n}}' > main.go

# Build
RUN go build -o main .

# Final stage  
FROM alpine:latest

RUN apk --no-cache add ca-certificates
WORKDIR /root/

COPY --from=builder /app/main .

CMD ["./main"]
"""

        return dockerfile_content.strip(), []


class ProtocolSchemeProcessor:
    """Main processor for protocol schemes."""

    def __init__(self):
        """Initialize with available handlers."""
        self.handlers: Dict[str, ProtocolSchemeHandler] = {}
        self._register_default_handlers()

    def _register_default_handlers(self):
        """Register default protocol handlers."""
        handlers = [
            UvxSchemeHandler(),
            NpxSchemeHandler(),
            GoSchemeHandler(),
        ]
        
        for handler in handlers:
            self.handlers[handler.get_scheme_name()] = handler

    def register_handler(self, handler: ProtocolSchemeHandler):
        """Register a custom protocol handler."""
        self.handlers[handler.get_scheme_name()] = handler

    def is_protocol_scheme(self, image_or_url: str) -> bool:
        """Check if the given string is a protocol scheme URL."""
        if "://" not in image_or_url:
            return False
        
        scheme = image_or_url.split("://", 1)[0]
        return scheme in self.handlers

    def get_supported_schemes(self) -> List[str]:
        """Get list of supported protocol schemes."""
        return list(self.handlers.keys())

    async def process_scheme(self, scheme_url: str) -> Tuple[str, str, List[str]]:
        """
        Process a protocol scheme URL.
        
        Returns:
            Tuple of (dockerfile_content, image_tag, build_args)
        """
        if not self.is_protocol_scheme(scheme_url):
            raise ProtocolSchemeError(f"Unsupported or invalid protocol scheme: {scheme_url}")

        scheme = scheme_url.split("://", 1)[0]
        handler = self.handlers[scheme]

        # Create temporary build context
        with tempfile.TemporaryDirectory() as temp_dir:
            build_context = Path(temp_dir)
            
            try:
                dockerfile_content, build_args = await handler.process(scheme_url, build_context)
                
                # Generate image tag
                image_tag = self._generate_image_tag(scheme_url)
                
                # Write Dockerfile to build context
                dockerfile_path = build_context / "Dockerfile"
                with open(dockerfile_path, 'w') as f:
                    f.write(dockerfile_content)
                
                logger.info(f"Generated Dockerfile for {scheme_url}")
                logger.debug(f"Dockerfile content:\n{dockerfile_content}")
                
                return dockerfile_content, image_tag, build_args
            
            except Exception as e:
                logger.error(f"Failed to process protocol scheme {scheme_url}: {e}")
                raise ProtocolSchemeError(f"Failed to process {scheme_url}: {e}")

    def _generate_image_tag(self, scheme_url: str) -> str:
        """Generate a Docker image tag from the scheme URL."""
        # Parse the URL
        parsed = urlparse(scheme_url)
        scheme = parsed.scheme
        path = parsed.netloc + parsed.path
        
        # Clean up the path for use as image tag
        # Replace special characters with hyphens
        clean_path = re.sub(r'[^a-zA-Z0-9._-]', '-', path)
        # Remove consecutive hyphens
        clean_path = re.sub(r'-+', '-', clean_path).strip('-')
        
        # Generate tag
        tag = f"mcpm-{scheme}-{clean_path}:latest"
        
        # Ensure tag is valid (lowercase, etc.)
        tag = tag.lower()
        
        return tag

    async def build_image_from_scheme(
        self, 
        scheme_url: str, 
        docker_client, 
        force_rebuild: bool = False
    ) -> str:
        """
        Build Docker image from protocol scheme.
        
        Returns:
            The built image tag
        """
        dockerfile_content, image_tag, build_args = await self.process_scheme(scheme_url)
        
        # Check if image already exists
        if not force_rebuild:
            exists = await docker_client.image_exists(image_tag)
            if exists:
                logger.info(f"Image {image_tag} already exists, skipping build")
                return image_tag

        # Create temporary build context
        with tempfile.TemporaryDirectory() as temp_dir:
            build_context = Path(temp_dir)
            
            # Write Dockerfile
            dockerfile_path = build_context / "Dockerfile"
            with open(dockerfile_path, 'w') as f:
                f.write(dockerfile_content)
            
            # If this is a local Go project, the source was already copied
            # during process_scheme, so we need to redo that
            if scheme_url.startswith("go://") and ("/" in scheme_url[5:] or scheme_url[5:] == "."):
                scheme = scheme_url.split("://", 1)[0]
                handler = self.handlers[scheme]
                await handler.process(scheme_url, build_context)
            
            # Build the image
            logger.info(f"Building image {image_tag} from {scheme_url}")
            await docker_client.build_image(
                path=str(build_context),
                tag=image_tag,
                build_args=dict(build_args) if build_args else None
            )
            
            logger.info(f"Successfully built image {image_tag}")
            return image_tag


# Global processor instance
_processor = None

def get_protocol_processor() -> ProtocolSchemeProcessor:
    """Get the global protocol scheme processor."""
    global _processor
    if _processor is None:
        _processor = ProtocolSchemeProcessor()
    return _processor