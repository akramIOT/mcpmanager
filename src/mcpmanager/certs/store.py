"""Certificate metadata storage and management."""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class CertificateStore:
    """Storage and metadata management for certificates."""

    def __init__(self, config_dir: Path):
        """Initialize certificate store."""
        self.config_dir = config_dir
        self.metadata_file = config_dir / "certificate_metadata.json"
        self._metadata: Dict[str, Any] = {}
        self._load_metadata()

    def _load_metadata(self) -> None:
        """Load certificate metadata from disk."""
        try:
            if self.metadata_file.exists():
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    self._metadata = json.load(f)
                logger.debug(f"Loaded certificate metadata: {len(self._metadata)} entries")
            else:
                self._metadata = {}
        except Exception as e:
            logger.error(f"Failed to load certificate metadata: {e}")
            self._metadata = {}

    def _save_metadata(self) -> None:
        """Save certificate metadata to disk."""
        try:
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(self._metadata, f, indent=2, default=str)
            logger.debug("Saved certificate metadata")
        except Exception as e:
            logger.error(f"Failed to save certificate metadata: {e}")

    async def store_certificate_metadata(self, cert_name: str, metadata: Dict[str, Any]) -> None:
        """Store metadata for a certificate."""
        try:
            self._metadata[cert_name] = {
                **metadata,
                "updated_at": datetime.now().isoformat()
            }
            self._save_metadata()
            logger.debug(f"Stored metadata for certificate: {cert_name}")
        except Exception as e:
            logger.error(f"Failed to store metadata for {cert_name}: {e}")

    async def get_certificate_metadata(self, cert_name: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a certificate."""
        return self._metadata.get(cert_name)

    async def remove_certificate_metadata(self, cert_name: str) -> bool:
        """Remove metadata for a certificate."""
        try:
            if cert_name in self._metadata:
                del self._metadata[cert_name]
                self._save_metadata()
                logger.debug(f"Removed metadata for certificate: {cert_name}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to remove metadata for {cert_name}: {e}")
            return False

    async def list_certificate_metadata(self) -> Dict[str, Any]:
        """List all certificate metadata."""
        return self._metadata.copy()

    async def search_certificates(self, query: str) -> Dict[str, Any]:
        """Search certificates by subject, issuer, or name."""
        results = {}
        query_lower = query.lower()
        
        for cert_name, metadata in self._metadata.items():
            # Search in certificate name
            if query_lower in cert_name.lower():
                results[cert_name] = metadata
                continue
            
            # Search in subject
            subject = metadata.get("subject", "")
            if query_lower in subject.lower():
                results[cert_name] = metadata
                continue
            
            # Search in issuer
            issuer = metadata.get("issuer", "")
            if query_lower in issuer.lower():
                results[cert_name] = metadata
                continue
        
        return results

    async def get_expiring_certificates(self, days_threshold: int = 30) -> Dict[str, Any]:
        """Get certificates expiring within threshold days."""
        expiring = {}
        current_time = datetime.now()
        
        for cert_name, metadata in self._metadata.items():
            try:
                not_after_str = metadata.get("not_after")
                if not_after_str:
                    not_after = datetime.fromisoformat(not_after_str.replace('Z', '+00:00'))
                    days_until_expiry = (not_after - current_time).days
                    
                    if 0 <= days_until_expiry <= days_threshold:
                        expiring[cert_name] = {
                            **metadata,
                            "days_until_expiry": days_until_expiry
                        }
            except Exception as e:
                logger.warning(f"Failed to check expiry for {cert_name}: {e}")
        
        return expiring

    async def get_expired_certificates(self) -> Dict[str, Any]:
        """Get all expired certificates."""
        expired = {}
        current_time = datetime.now()
        
        for cert_name, metadata in self._metadata.items():
            try:
                not_after_str = metadata.get("not_after")
                if not_after_str:
                    not_after = datetime.fromisoformat(not_after_str.replace('Z', '+00:00'))
                    
                    if not_after < current_time:
                        days_expired = (current_time - not_after).days
                        expired[cert_name] = {
                            **metadata,
                            "days_expired": days_expired
                        }
            except Exception as e:
                logger.warning(f"Failed to check expiry for {cert_name}: {e}")
        
        return expired

    async def update_certificate_metadata(self, cert_name: str, updates: Dict[str, Any]) -> bool:
        """Update specific fields in certificate metadata."""
        try:
            if cert_name in self._metadata:
                self._metadata[cert_name].update(updates)
                self._metadata[cert_name]["updated_at"] = datetime.now().isoformat()
                self._save_metadata()
                logger.debug(f"Updated metadata for certificate: {cert_name}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to update metadata for {cert_name}: {e}")
            return False

    async def add_certificate_tag(self, cert_name: str, tag: str) -> bool:
        """Add a tag to a certificate."""
        try:
            if cert_name in self._metadata:
                tags = self._metadata[cert_name].get("tags", [])
                if tag not in tags:
                    tags.append(tag)
                    self._metadata[cert_name]["tags"] = tags
                    self._metadata[cert_name]["updated_at"] = datetime.now().isoformat()
                    self._save_metadata()
                logger.debug(f"Added tag '{tag}' to certificate: {cert_name}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to add tag to {cert_name}: {e}")
            return False

    async def remove_certificate_tag(self, cert_name: str, tag: str) -> bool:
        """Remove a tag from a certificate."""
        try:
            if cert_name in self._metadata:
                tags = self._metadata[cert_name].get("tags", [])
                if tag in tags:
                    tags.remove(tag)
                    self._metadata[cert_name]["tags"] = tags
                    self._metadata[cert_name]["updated_at"] = datetime.now().isoformat()
                    self._save_metadata()
                logger.debug(f"Removed tag '{tag}' from certificate: {cert_name}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to remove tag from {cert_name}: {e}")
            return False

    async def get_certificates_by_tag(self, tag: str) -> Dict[str, Any]:
        """Get all certificates with a specific tag."""
        results = {}
        
        for cert_name, metadata in self._metadata.items():
            tags = metadata.get("tags", [])
            if tag in tags:
                results[cert_name] = metadata
        
        return results

    async def get_certificate_statistics(self) -> Dict[str, Any]:
        """Get statistics about stored certificates."""
        total_certs = len(self._metadata)
        ca_certs = 0
        expired_count = 0
        expiring_count = 0
        current_time = datetime.now()
        
        for metadata in self._metadata.values():
            # Count CA certificates
            if metadata.get("type") == "ca":
                ca_certs += 1
            
            # Count expired and expiring
            try:
                not_after_str = metadata.get("not_after")
                if not_after_str:
                    not_after = datetime.fromisoformat(not_after_str.replace('Z', '+00:00'))
                    
                    if not_after < current_time:
                        expired_count += 1
                    elif (not_after - current_time).days <= 30:
                        expiring_count += 1
            except Exception:
                pass
        
        return {
            "total_certificates": total_certs,
            "ca_certificates": ca_certs,
            "client_certificates": total_certs - ca_certs,
            "expired_certificates": expired_count,
            "expiring_certificates": expiring_count,
            "metadata_file": str(self.metadata_file),
            "last_updated": max(
                (metadata.get("updated_at", "") for metadata in self._metadata.values()),
                default=""
            )
        }

    async def export_metadata(self, export_path: str) -> None:
        """Export certificate metadata to a file."""
        try:
            export_file = Path(export_path)
            
            export_data = {
                "exported_at": datetime.now().isoformat(),
                "total_certificates": len(self._metadata),
                "certificates": self._metadata
            }
            
            with open(export_file, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, default=str)
            
            logger.info(f"Exported certificate metadata to: {export_path}")
            
        except Exception as e:
            logger.error(f"Failed to export metadata: {e}")
            raise

    async def import_metadata(self, import_path: str, merge: bool = True) -> int:
        """Import certificate metadata from a file."""
        try:
            import_file = Path(import_path)
            if not import_file.exists():
                raise FileNotFoundError(f"Import file not found: {import_path}")
            
            with open(import_file, 'r', encoding='utf-8') as f:
                import_data = json.load(f)
            
            imported_metadata = import_data.get("certificates", {})
            imported_count = 0
            
            if merge:
                # Merge with existing metadata
                for cert_name, metadata in imported_metadata.items():
                    self._metadata[cert_name] = metadata
                    imported_count += 1
            else:
                # Replace existing metadata
                self._metadata = imported_metadata.copy()
                imported_count = len(imported_metadata)
            
            self._save_metadata()
            logger.info(f"Imported {imported_count} certificate metadata entries")
            
            return imported_count
            
        except Exception as e:
            logger.error(f"Failed to import metadata: {e}")
            raise

    async def backup_metadata(self, backup_dir: Optional[str] = None) -> str:
        """Create a backup of certificate metadata."""
        try:
            if backup_dir:
                backup_path = Path(backup_dir)
            else:
                backup_path = self.config_dir / "backups"
            
            backup_path.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = backup_path / f"certificate_metadata_backup_{timestamp}.json"
            
            await self.export_metadata(str(backup_file))
            
            logger.info(f"Created metadata backup: {backup_file}")
            return str(backup_file)
            
        except Exception as e:
            logger.error(f"Failed to create metadata backup: {e}")
            raise