"""Certificate validation utilities."""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Any
import hashlib

from cryptography import x509
from cryptography.x509.verification import PolicyBuilder, StoreBuilder

logger = logging.getLogger(__name__)


class CertificateValidator:
    """Certificate validation and verification utilities."""

    def __init__(self):
        """Initialize certificate validator."""
        pass

    async def validate_certificate(self, cert: x509.Certificate) -> Dict[str, Any]:
        """Validate a certificate and return detailed results."""
        errors = []
        warnings = []
        
        try:
            current_time = datetime.now(timezone.utc)
            
            # Check validity period
            if cert.not_valid_before > current_time:
                errors.append("Certificate is not yet valid")
            
            if cert.not_valid_after < current_time:
                errors.append("Certificate has expired")
            
            # Check if expiring soon (within 30 days)
            days_until_expiry = (cert.not_valid_after - current_time).days
            if 0 < days_until_expiry <= 30:
                warnings.append(f"Certificate expires in {days_until_expiry} days")
            
            # Validate subject
            subject = cert.subject
            if not subject:
                errors.append("Certificate has no subject")
            else:
                # Check for common name
                cn_attributes = subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
                if not cn_attributes:
                    warnings.append("Certificate has no Common Name")
            
            # Validate key usage
            try:
                key_usage = cert.extensions.get_extension_for_oid(x509.oid.ExtensionOID.KEY_USAGE)
                if not key_usage.value.digital_signature:
                    warnings.append("Certificate does not allow digital signatures")
            except x509.ExtensionNotFound:
                warnings.append("Certificate has no Key Usage extension")
            
            # Check public key algorithm and size
            public_key = cert.public_key()
            if hasattr(public_key, 'key_size'):
                key_size = public_key.key_size
                if key_size < 2048:
                    warnings.append(f"Weak key size: {key_size} bits")
            
            # Check signature algorithm
            sig_alg = cert.signature_algorithm_oid._name
            weak_algorithms = ['md5', 'sha1']
            if any(weak_alg in sig_alg.lower() for weak_alg in weak_algorithms):
                warnings.append(f"Weak signature algorithm: {sig_alg}")
            
            # Validate certificate chain (if self-signed)
            if cert.issuer == cert.subject:
                # Self-signed certificate
                try:
                    # Verify self-signature
                    public_key.verify(
                        cert.signature,
                        cert.tbs_certificate_bytes,
                        cert.signature_algorithm_oid
                    )
                except Exception as e:
                    errors.append(f"Invalid self-signature: {e}")
            
            return {
                "valid": len(errors) == 0,
                "errors": errors,
                "warnings": warnings,
                "subject": str(cert.subject),
                "issuer": str(cert.issuer),
                "not_before": cert.not_valid_before.isoformat(),
                "not_after": cert.not_valid_after.isoformat(),
                "days_until_expiry": days_until_expiry,
                "is_self_signed": cert.issuer == cert.subject,
                "key_algorithm": public_key.algorithm.name,
                "key_size": getattr(public_key, 'key_size', None),
                "signature_algorithm": sig_alg
            }
            
        except Exception as e:
            logger.error(f"Certificate validation failed: {e}")
            return {
                "valid": False,
                "errors": [f"Validation error: {e}"],
                "warnings": [],
                "validation_error": str(e)
            }

    async def validate_certificate_chain(
        self, 
        cert_chain: List[x509.Certificate],
        trusted_roots: List[x509.Certificate]
    ) -> Dict[str, Any]:
        """Validate a complete certificate chain."""
        try:
            if not cert_chain:
                return {
                    "valid": False,
                    "errors": ["Empty certificate chain"]
                }
            
            errors = []
            warnings = []
            
            # Build trust store
            store_builder = StoreBuilder()
            for root_cert in trusted_roots:
                store_builder = store_builder.add_certs([root_cert])
            
            trust_store = store_builder.build()
            
            # Build validation policy
            policy_builder = PolicyBuilder().store(trust_store)
            policy = policy_builder.build()
            
            # Validate chain
            leaf_cert = cert_chain[0]
            intermediates = cert_chain[1:] if len(cert_chain) > 1 else []
            
            try:
                # Perform chain validation
                chain = policy.validate(leaf_cert, intermediates)
                
                return {
                    "valid": True,
                    "errors": [],
                    "warnings": warnings,
                    "chain_length": len(chain),
                    "leaf_certificate": str(leaf_cert.subject),
                    "root_certificate": str(chain[-1].subject) if chain else None
                }
                
            except Exception as e:
                errors.append(f"Chain validation failed: {e}")
                
                return {
                    "valid": False,
                    "errors": errors,
                    "warnings": warnings,
                    "validation_error": str(e)
                }
                
        except Exception as e:
            logger.error(f"Certificate chain validation failed: {e}")
            return {
                "valid": False,
                "errors": [f"Chain validation error: {e}"]
            }

    async def check_certificate_revocation(self, cert: x509.Certificate) -> Dict[str, Any]:
        """Check certificate revocation status (CRL/OCSP)."""
        # This is a placeholder for revocation checking
        # In a full implementation, this would:
        # 1. Check for CRL Distribution Points extension
        # 2. Download and verify CRL
        # 3. Check for OCSP responder extension
        # 4. Query OCSP responder
        
        logger.info("Certificate revocation checking not yet implemented")
        return {
            "revocation_checked": False,
            "revoked": False,
            "reason": "Revocation checking not implemented"
        }

    def extract_certificate_domains(self, cert: x509.Certificate) -> List[str]:
        """Extract all domains/hostnames from certificate."""
        domains = []
        
        # Get Common Name
        try:
            cn_attributes = cert.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
            if cn_attributes:
                domains.append(cn_attributes[0].value)
        except Exception:
            pass
        
        # Get Subject Alternative Names
        try:
            san_ext = cert.extensions.get_extension_for_oid(x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
            for name in san_ext.value:
                if isinstance(name, x509.DNSName):
                    domains.append(name.value)
                elif isinstance(name, x509.IPAddress):
                    domains.append(str(name.value))
        except x509.ExtensionNotFound:
            pass
        
        return list(set(domains))  # Remove duplicates

    def match_hostname(self, cert: x509.Certificate, hostname: str) -> bool:
        """Check if certificate matches the given hostname."""
        domains = self.extract_certificate_domains(cert)
        
        for domain in domains:
            # Exact match
            if domain == hostname:
                return True
            
            # Wildcard match
            if domain.startswith('*.'):
                domain_suffix = domain[2:]
                if hostname.endswith(domain_suffix):
                    # Ensure wildcard only matches one level
                    hostname_prefix = hostname[:-len(domain_suffix)-1]
                    if '.' not in hostname_prefix:
                        return True
        
        return False

    def get_certificate_fingerprint(self, cert: x509.Certificate, algorithm: str = "sha256") -> str:
        """Get certificate fingerprint using specified algorithm."""
        cert_bytes = cert.public_bytes(x509.Encoding.DER)
        
        if algorithm.lower() == "sha256":
            return hashlib.sha256(cert_bytes).hexdigest()
        elif algorithm.lower() == "sha1":
            return hashlib.sha1(cert_bytes).hexdigest()
        elif algorithm.lower() == "md5":
            return hashlib.md5(cert_bytes).hexdigest()
        else:
            raise ValueError(f"Unsupported fingerprint algorithm: {algorithm}")

    def compare_certificates(self, cert1: x509.Certificate, cert2: x509.Certificate) -> Dict[str, Any]:
        """Compare two certificates and return differences."""
        differences = []
        
        if cert1.subject != cert2.subject:
            differences.append("Different subjects")
        
        if cert1.issuer != cert2.issuer:
            differences.append("Different issuers")
        
        if cert1.not_valid_before != cert2.not_valid_before:
            differences.append("Different validity start dates")
        
        if cert1.not_valid_after != cert2.not_valid_after:
            differences.append("Different validity end dates")
        
        if cert1.serial_number != cert2.serial_number:
            differences.append("Different serial numbers")
        
        # Compare public keys
        cert1_key_bytes = cert1.public_key().public_bytes(
            x509.Encoding.DER,
            x509.PublicFormat.SubjectPublicKeyInfo
        )
        cert2_key_bytes = cert2.public_key().public_bytes(
            x509.Encoding.DER,
            x509.PublicFormat.SubjectPublicKeyInfo
        )
        
        if cert1_key_bytes != cert2_key_bytes:
            differences.append("Different public keys")
        
        return {
            "identical": len(differences) == 0,
            "differences": differences,
            "cert1_fingerprint": self.get_certificate_fingerprint(cert1),
            "cert2_fingerprint": self.get_certificate_fingerprint(cert2)
        }

    async def validate_certificate_file(self, file_path: str) -> Dict[str, Any]:
        """Validate a certificate file."""
        try:
            from pathlib import Path
            
            cert_file = Path(file_path)
            if not cert_file.exists():
                return {
                    "valid": False,
                    "errors": [f"File not found: {file_path}"]
                }
            
            cert_data = cert_file.read_bytes()
            
            # Try to load as PEM
            try:
                cert = x509.load_pem_x509_certificate(cert_data)
            except ValueError:
                # Try to load as DER
                try:
                    cert = x509.load_der_x509_certificate(cert_data)
                except ValueError:
                    return {
                        "valid": False,
                        "errors": ["Invalid certificate format (not PEM or DER)"]
                    }
            
            # Validate certificate
            validation_result = await self.validate_certificate(cert)
            validation_result["file_path"] = file_path
            validation_result["file_size"] = len(cert_data)
            
            return validation_result
            
        except Exception as e:
            logger.error(f"Certificate file validation failed: {e}")
            return {
                "valid": False,
                "errors": [f"File validation error: {e}"],
                "file_path": file_path
            }