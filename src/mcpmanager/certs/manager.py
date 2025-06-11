"""Certificate management system."""

import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timezone
import ssl
import hashlib

import httpx
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption

from .validator import CertificateValidator
from .store import CertificateStore

logger = logging.getLogger(__name__)


class CertificateManager:
    """Comprehensive certificate management system."""

    def __init__(self, config_dir: Optional[Path] = None):
        """Initialize certificate manager."""
        self.config_dir = config_dir or Path.home() / ".mcpmanager" / "certs"
        self.ca_dir = self.config_dir / "ca"
        self.client_dir = self.config_dir / "client"
        self.trusted_dir = self.config_dir / "trusted"
        
        # Ensure directories exist
        for directory in [self.config_dir, self.ca_dir, self.client_dir, self.trusted_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        
        self.validator = CertificateValidator()
        self.store = CertificateStore(self.config_dir)
        
        # Initialize system CA bundle
        self._system_ca_bundle = None
        self._custom_ca_bundle = None

    async def initialize(self) -> None:
        """Initialize certificate manager."""
        try:
            # Load system CA bundle
            self._system_ca_bundle = self._get_system_ca_bundle()
            
            # Create custom CA bundle from trusted directory
            await self._update_custom_ca_bundle()
            
            logger.info("Certificate manager initialized")
        except Exception as e:
            logger.error(f"Failed to initialize certificate manager: {e}")
            raise

    def _get_system_ca_bundle(self) -> Optional[Path]:
        """Get system CA bundle path."""
        # Common locations for CA bundles
        ca_bundle_paths = [
            "/etc/ssl/certs/ca-certificates.crt",  # Debian/Ubuntu
            "/etc/pki/tls/certs/ca-bundle.crt",    # RHEL/CentOS
            "/etc/ssl/ca-bundle.pem",              # OpenSUSE
            "/usr/local/share/certs/ca-root-nss.crt",  # FreeBSD
            "/etc/pki/tls/cert.pem",               # Amazon Linux
        ]
        
        for path in ca_bundle_paths:
            if Path(path).exists():
                return Path(path)
        
        # Try to get from requests/certifi
        try:
            import certifi
            return Path(certifi.where())
        except ImportError:
            pass
        
        # Fallback to SSL module default
        try:
            return Path(ssl.get_default_verify_paths().cafile)
        except Exception:
            pass
        
        logger.warning("Could not find system CA bundle")
        return None

    async def _update_custom_ca_bundle(self) -> None:
        """Update custom CA bundle with trusted certificates."""
        try:
            custom_bundle_path = self.config_dir / "ca-bundle.pem"
            
            # Start with system CA bundle if available
            content = ""
            if self._system_ca_bundle and self._system_ca_bundle.exists():
                content = self._system_ca_bundle.read_text()
            
            # Add custom trusted certificates
            for cert_file in self.trusted_dir.glob("*.pem"):
                content += f"\n# {cert_file.name}\n"
                content += cert_file.read_text()
                content += "\n"
            
            for cert_file in self.trusted_dir.glob("*.crt"):
                content += f"\n# {cert_file.name}\n"
                content += cert_file.read_text()
                content += "\n"
            
            # Write custom bundle
            custom_bundle_path.write_text(content)
            self._custom_ca_bundle = custom_bundle_path
            
            # Set environment variable for applications to use
            os.environ["REQUESTS_CA_BUNDLE"] = str(custom_bundle_path)
            os.environ["CURL_CA_BUNDLE"] = str(custom_bundle_path)
            
            logger.info(f"Updated custom CA bundle: {custom_bundle_path}")
            
        except Exception as e:
            logger.error(f"Failed to update custom CA bundle: {e}")

    async def add_trusted_ca(self, cert_data: Union[str, bytes], name: Optional[str] = None) -> str:
        """Add a trusted CA certificate."""
        try:
            # Parse certificate
            if isinstance(cert_data, str):
                cert_data = cert_data.encode()
            
            cert = x509.load_pem_x509_certificate(cert_data)
            
            # Validate certificate
            validation_result = await self.validator.validate_certificate(cert)
            if not validation_result["valid"]:
                raise ValueError(f"Invalid certificate: {validation_result['errors']}")
            
            # Generate name if not provided
            if not name:
                subject = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
                if subject:
                    name = subject[0].value.replace(" ", "_").replace(".", "_")
                else:
                    # Use certificate hash as name
                    cert_hash = hashlib.sha256(cert_data).hexdigest()[:8]
                    name = f"ca_{cert_hash}"
            
            # Ensure .pem extension
            if not name.endswith('.pem'):
                name += '.pem'
            
            # Save to trusted directory
            cert_path = self.trusted_dir / name
            cert_path.write_bytes(cert_data)
            
            # Store metadata
            await self.store.store_certificate_metadata(name, {
                "type": "ca",
                "subject": str(cert.subject),
                "issuer": str(cert.issuer),
                "not_before": cert.not_valid_before.isoformat(),
                "not_after": cert.not_valid_after.isoformat(),
                "serial_number": str(cert.serial_number),
                "fingerprint": hashlib.sha256(cert_data).hexdigest(),
                "added_at": datetime.now(timezone.utc).isoformat()
            })
            
            # Update custom CA bundle
            await self._update_custom_ca_bundle()
            
            logger.info(f"Added trusted CA certificate: {name}")
            return name
            
        except Exception as e:
            logger.error(f"Failed to add trusted CA: {e}")
            raise

    async def remove_trusted_ca(self, name: str) -> bool:
        """Remove a trusted CA certificate."""
        try:
            cert_path = self.trusted_dir / name
            if not cert_path.exists():
                return False
            
            # Remove certificate file
            cert_path.unlink()
            
            # Remove metadata
            await self.store.remove_certificate_metadata(name)
            
            # Update custom CA bundle
            await self._update_custom_ca_bundle()
            
            logger.info(f"Removed trusted CA certificate: {name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to remove trusted CA {name}: {e}")
            return False

    async def list_trusted_cas(self) -> List[Dict[str, Any]]:
        """List all trusted CA certificates."""
        try:
            cas = []
            
            for cert_file in self.trusted_dir.glob("*.pem"):
                try:
                    # Load certificate
                    cert_data = cert_file.read_bytes()
                    cert = x509.load_pem_x509_certificate(cert_data)
                    
                    # Get metadata
                    metadata = await self.store.get_certificate_metadata(cert_file.name)
                    
                    cas.append({
                        "name": cert_file.name,
                        "subject": str(cert.subject),
                        "issuer": str(cert.issuer),
                        "not_before": cert.not_valid_before.isoformat(),
                        "not_after": cert.not_valid_after.isoformat(),
                        "is_expired": cert.not_valid_after < datetime.now(timezone.utc),
                        "fingerprint": hashlib.sha256(cert_data).hexdigest(),
                        "metadata": metadata
                    })
                    
                except Exception as e:
                    logger.warning(f"Failed to process certificate {cert_file.name}: {e}")
            
            return sorted(cas, key=lambda x: x["subject"])
            
        except Exception as e:
            logger.error(f"Failed to list trusted CAs: {e}")
            return []

    async def download_ca_from_url(self, url: str, name: Optional[str] = None) -> str:
        """Download CA certificate from URL."""
        try:
            async with httpx.AsyncClient(verify=False) as client:  # Disable verification for downloading CAs
                response = await client.get(url)
                response.raise_for_status()
                
                cert_data = response.content
                
                # Try to parse as PEM
                try:
                    x509.load_pem_x509_certificate(cert_data)
                except ValueError:
                    # Try to parse as DER
                    try:
                        cert = x509.load_der_x509_certificate(cert_data)
                        # Convert to PEM
                        cert_data = cert.public_bytes(Encoding.PEM)
                    except ValueError:
                        raise ValueError("Invalid certificate format")
                
                # Use URL domain as name if not provided
                if not name:
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    name = parsed.hostname or "downloaded_ca"
                
                return await self.add_trusted_ca(cert_data, name)
                
        except Exception as e:
            logger.error(f"Failed to download CA from {url}: {e}")
            raise

    async def extract_ca_from_server(self, hostname: str, port: int = 443, name: Optional[str] = None) -> str:
        """Extract CA certificate from server's certificate chain."""
        try:
            # Connect to server and get certificate chain
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            
            with ssl.create_connection((hostname, port)) as sock:
                with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert_der = ssock.getpeercert(binary_form=True)
                    cert_chain = ssock.getpeercert_chain()
            
            if not cert_chain:
                raise ValueError("No certificate chain received")
            
            # Find root CA (self-signed certificate)
            root_ca = None
            for cert in cert_chain:
                if cert.issuer == cert.subject:  # Self-signed
                    root_ca = cert
                    break
            
            if not root_ca:
                # Use the last certificate in chain (likely root)
                root_ca = cert_chain[-1]
            
            # Convert to PEM
            cert_pem = root_ca.public_bytes(Encoding.PEM)
            
            # Use hostname as name if not provided
            if not name:
                name = f"{hostname}_ca"
            
            return await self.add_trusted_ca(cert_pem, name)
            
        except Exception as e:
            logger.error(f"Failed to extract CA from {hostname}:{port}: {e}")
            raise

    async def verify_server_certificate(self, hostname: str, port: int = 443) -> Dict[str, Any]:
        """Verify server certificate against trusted CAs."""
        try:
            # Create SSL context with custom CA bundle
            context = ssl.create_default_context()
            if self._custom_ca_bundle:
                context.load_verify_locations(str(self._custom_ca_bundle))
            
            # Connect and verify
            with ssl.create_connection((hostname, port)) as sock:
                with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert_der = ssock.getpeercert(binary_form=True)
                    cert_info = ssock.getpeercert()
            
            # Parse certificate
            cert = x509.load_der_x509_certificate(cert_der)
            
            return {
                "valid": True,
                "hostname": hostname,
                "port": port,
                "subject": str(cert.subject),
                "issuer": str(cert.issuer),
                "not_before": cert.not_valid_before.isoformat(),
                "not_after": cert.not_valid_after.isoformat(),
                "is_expired": cert.not_valid_after < datetime.now(timezone.utc),
                "san": self._get_san_from_cert(cert),
                "fingerprint": hashlib.sha256(cert_der).hexdigest(),
                "verification_time": datetime.now(timezone.utc).isoformat()
            }
            
        except ssl.SSLError as e:
            return {
                "valid": False,
                "hostname": hostname,
                "port": port,
                "error": str(e),
                "error_type": "ssl_error",
                "verification_time": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            return {
                "valid": False,
                "hostname": hostname,
                "port": port,
                "error": str(e),
                "error_type": "connection_error",
                "verification_time": datetime.now(timezone.utc).isoformat()
            }

    def _get_san_from_cert(self, cert: x509.Certificate) -> List[str]:
        """Extract Subject Alternative Names from certificate."""
        try:
            san_ext = cert.extensions.get_extension_for_oid(x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
            return [name.value for name in san_ext.value]
        except x509.ExtensionNotFound:
            return []

    async def generate_self_signed_cert(
        self, 
        common_name: str,
        san_names: Optional[List[str]] = None,
        key_size: int = 2048,
        valid_days: int = 365
    ) -> Dict[str, str]:
        """Generate self-signed certificate for testing."""
        try:
            # Generate private key
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=key_size,
            )
            
            # Create certificate
            subject = issuer = x509.Name([
                x509.NameAttribute(NameOID.COMMON_NAME, common_name),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "MCPManager"),
                x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "Development"),
            ])
            
            builder = x509.CertificateBuilder()
            builder = builder.subject_name(subject)
            builder = builder.issuer_name(issuer)
            builder = builder.public_key(private_key.public_key())
            builder = builder.serial_number(x509.random_serial_number())
            builder = builder.not_valid_before(datetime.now(timezone.utc))
            builder = builder.not_valid_after(datetime.now(timezone.utc).replace(day=datetime.now().day + valid_days))
            
            # Add SAN extension
            if san_names:
                san_list = [x509.DNSName(name) for name in san_names]
                builder = builder.add_extension(
                    x509.SubjectAlternativeName(san_list),
                    critical=False,
                )
            
            # Sign certificate
            certificate = builder.sign(private_key, hashes.SHA256())
            
            # Serialize to PEM
            cert_pem = certificate.public_bytes(Encoding.PEM).decode()
            key_pem = private_key.private_bytes(
                Encoding.PEM,
                PrivateFormat.PKCS8,
                NoEncryption()
            ).decode()
            
            # Save to files
            cert_name = f"{common_name.replace('.', '_')}_cert.pem"
            key_name = f"{common_name.replace('.', '_')}_key.pem"
            
            cert_path = self.client_dir / cert_name
            key_path = self.client_dir / key_name
            
            cert_path.write_text(cert_pem)
            key_path.write_text(key_pem)
            
            # Set restrictive permissions on private key
            key_path.chmod(0o600)
            
            logger.info(f"Generated self-signed certificate: {cert_name}")
            
            return {
                "certificate_path": str(cert_path),
                "private_key_path": str(key_path),
                "certificate_pem": cert_pem,
                "private_key_pem": key_pem,
                "common_name": common_name,
                "san_names": san_names or [],
                "valid_days": valid_days
            }
            
        except Exception as e:
            logger.error(f"Failed to generate self-signed certificate: {e}")
            raise

    async def import_certificate_bundle(self, bundle_path: str) -> List[str]:
        """Import multiple certificates from a bundle file."""
        try:
            bundle_file = Path(bundle_path)
            if not bundle_file.exists():
                raise FileNotFoundError(f"Bundle file not found: {bundle_path}")
            
            content = bundle_file.read_text()
            
            # Split bundle into individual certificates
            cert_blocks = []
            current_cert = []
            in_cert = False
            
            for line in content.split('\n'):
                if '-----BEGIN CERTIFICATE-----' in line:
                    in_cert = True
                    current_cert = [line]
                elif '-----END CERTIFICATE-----' in line:
                    current_cert.append(line)
                    cert_blocks.append('\n'.join(current_cert))
                    current_cert = []
                    in_cert = False
                elif in_cert:
                    current_cert.append(line)
            
            # Import each certificate
            imported = []
            for i, cert_pem in enumerate(cert_blocks):
                try:
                    name = f"bundle_{bundle_file.stem}_{i+1}"
                    added_name = await self.add_trusted_ca(cert_pem, name)
                    imported.append(added_name)
                except Exception as e:
                    logger.warning(f"Failed to import certificate {i+1} from bundle: {e}")
            
            logger.info(f"Imported {len(imported)} certificates from bundle")
            return imported
            
        except Exception as e:
            logger.error(f"Failed to import certificate bundle: {e}")
            raise

    def get_ca_bundle_path(self) -> Optional[str]:
        """Get path to custom CA bundle."""
        return str(self._custom_ca_bundle) if self._custom_ca_bundle else None

    async def cleanup_expired_certificates(self) -> int:
        """Remove expired certificates and return count."""
        try:
            removed_count = 0
            current_time = datetime.now(timezone.utc)
            
            for cert_file in self.trusted_dir.glob("*.pem"):
                try:
                    cert_data = cert_file.read_bytes()
                    cert = x509.load_pem_x509_certificate(cert_data)
                    
                    if cert.not_valid_after < current_time:
                        logger.info(f"Removing expired certificate: {cert_file.name}")
                        await self.remove_trusted_ca(cert_file.name)
                        removed_count += 1
                        
                except Exception as e:
                    logger.warning(f"Failed to check certificate {cert_file.name}: {e}")
            
            if removed_count > 0:
                await self._update_custom_ca_bundle()
            
            return removed_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup expired certificates: {e}")
            return 0

    def get_certificate_info(self, cert_data: Union[str, bytes]) -> Dict[str, Any]:
        """Get detailed information about a certificate."""
        try:
            if isinstance(cert_data, str):
                cert_data = cert_data.encode()
            
            cert = x509.load_pem_x509_certificate(cert_data)
            
            return {
                "subject": str(cert.subject),
                "issuer": str(cert.issuer),
                "version": cert.version.name,
                "serial_number": str(cert.serial_number),
                "not_before": cert.not_valid_before.isoformat(),
                "not_after": cert.not_valid_after.isoformat(),
                "is_expired": cert.not_valid_after < datetime.now(timezone.utc),
                "signature_algorithm": cert.signature_algorithm_oid._name,
                "public_key_algorithm": cert.public_key().algorithm.name,
                "key_size": getattr(cert.public_key(), 'key_size', None),
                "san": self._get_san_from_cert(cert),
                "fingerprint_sha256": hashlib.sha256(cert_data).hexdigest(),
                "fingerprint_sha1": hashlib.sha1(cert_data).hexdigest(),
                "is_ca": self._is_ca_certificate(cert),
                "extensions": self._get_certificate_extensions(cert)
            }
            
        except Exception as e:
            logger.error(f"Failed to get certificate info: {e}")
            raise

    def _is_ca_certificate(self, cert: x509.Certificate) -> bool:
        """Check if certificate is a CA certificate."""
        try:
            basic_constraints = cert.extensions.get_extension_for_oid(x509.oid.ExtensionOID.BASIC_CONSTRAINTS)
            return basic_constraints.value.ca
        except x509.ExtensionNotFound:
            return False

    def _get_certificate_extensions(self, cert: x509.Certificate) -> List[Dict[str, Any]]:
        """Get certificate extensions information."""
        extensions = []
        for ext in cert.extensions:
            extensions.append({
                "oid": ext.oid._name,
                "critical": ext.critical,
                "value": str(ext.value)
            })
        return extensions

    def get_manager_summary(self) -> Dict[str, Any]:
        """Get certificate manager summary."""
        return {
            "config_dir": str(self.config_dir),
            "ca_bundle_path": self.get_ca_bundle_path(),
            "system_ca_bundle": str(self._system_ca_bundle) if self._system_ca_bundle else None,
            "trusted_ca_count": len(list(self.trusted_dir.glob("*.pem"))),
            "client_cert_count": len(list(self.client_dir.glob("*.pem"))),
        }