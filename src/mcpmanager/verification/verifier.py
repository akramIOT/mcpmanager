"""Core image verification functionality."""

import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
from enum import Enum

from mcpmanager.exceptions import MCPManagerError

logger = logging.getLogger(__name__)


class VerificationError(MCPManagerError):
    """Image verification error."""
    pass


class VerificationStatus(str, Enum):
    """Verification status values."""
    VERIFIED = "verified"
    FAILED = "failed"
    PARTIAL = "partial"
    SKIPPED = "skipped"


@dataclass
class SignatureInfo:
    """Signature information."""
    keyid: str
    signature: str
    algorithm: str
    timestamp: Optional[datetime] = None
    issuer: Optional[str] = None
    subject: Optional[str] = None


@dataclass
class AttestationInfo:
    """Attestation information."""
    type: str
    payload: Dict[str, Any]
    verified: bool
    timestamp: Optional[datetime] = None


@dataclass
class VerificationResult:
    """Result of image verification."""
    image: str
    digest: str
    status: VerificationStatus
    verified: bool
    timestamp: datetime
    signatures: List[SignatureInfo] = None
    attestations: List[AttestationInfo] = None
    policy_violations: List[str] = None
    metadata: Dict[str, Any] = None
    error: Optional[str] = None

    def __post_init__(self):
        """Initialize default values."""
        if self.signatures is None:
            self.signatures = []
        if self.attestations is None:
            self.attestations = []
        if self.policy_violations is None:
            self.policy_violations = []
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = asdict(self)
        result["timestamp"] = self.timestamp.isoformat()
        
        # Convert signature timestamps
        for sig in result["signatures"]:
            if sig["timestamp"]:
                sig["timestamp"] = sig["timestamp"].isoformat()
        
        # Convert attestation timestamps
        for att in result["attestations"]:
            if att["timestamp"]:
                att["timestamp"] = att["timestamp"].isoformat()
        
        return result


class ImageVerifier:
    """Main image verification system."""

    def __init__(self):
        """Initialize verifier."""
        self.verifiers = {}
        self._register_default_verifiers()

    def _register_default_verifiers(self):
        """Register default verification backends."""
        try:
            from .sigstore import SigstoreVerifier
            self.verifiers["sigstore"] = SigstoreVerifier()
        except ImportError:
            logger.warning("Sigstore verifier not available")

    def register_verifier(self, name: str, verifier):
        """Register a custom verifier."""
        self.verifiers[name] = verifier

    async def verify_image(
        self,
        image: str,
        verification_config: Optional[Dict[str, Any]] = None
    ) -> VerificationResult:
        """Verify an image using configured verifiers."""
        if not verification_config:
            return VerificationResult(
                image=image,
                digest="",
                status=VerificationStatus.SKIPPED,
                verified=True,  # Default to true when no verification requested
                timestamp=datetime.now(timezone.utc),
                metadata={"reason": "No verification configuration provided"}
            )

        try:
            # Get image digest
            digest = await self._get_image_digest(image)
            
            # Initialize result
            result = VerificationResult(
                image=image,
                digest=digest,
                status=VerificationStatus.VERIFIED,
                verified=True,
                timestamp=datetime.now(timezone.utc)
            )

            verification_methods = verification_config.get("methods", [])
            if not verification_methods:
                result.status = VerificationStatus.SKIPPED
                result.metadata["reason"] = "No verification methods specified"
                return result

            # Run verification methods
            all_verified = True
            for method_config in verification_methods:
                method_name = method_config.get("type")
                if method_name not in self.verifiers:
                    logger.warning(f"Verification method '{method_name}' not available")
                    continue

                try:
                    verifier = self.verifiers[method_name]
                    method_result = await verifier.verify(image, digest, method_config)
                    
                    # Merge results
                    result.signatures.extend(method_result.get("signatures", []))
                    result.attestations.extend(method_result.get("attestations", []))
                    
                    if not method_result.get("verified", False):
                        all_verified = False
                        result.policy_violations.extend(method_result.get("violations", []))

                except Exception as e:
                    logger.error(f"Verification method '{method_name}' failed: {e}")
                    all_verified = False
                    result.policy_violations.append(f"{method_name}: {str(e)}")

            # Set final verification status
            result.verified = all_verified
            if not all_verified:
                result.status = VerificationStatus.FAILED if result.policy_violations else VerificationStatus.PARTIAL

            # Apply verification policy
            policy_config = verification_config.get("policy")
            if policy_config:
                policy_result = await self._apply_verification_policy(result, policy_config)
                if not policy_result["allowed"]:
                    result.verified = False
                    result.status = VerificationStatus.FAILED
                    result.policy_violations.extend(policy_result["violations"])

            return result

        except Exception as e:
            logger.error(f"Image verification failed for {image}: {e}")
            return VerificationResult(
                image=image,
                digest="",
                status=VerificationStatus.FAILED,
                verified=False,
                timestamp=datetime.now(timezone.utc),
                error=str(e)
            )

    async def _get_image_digest(self, image: str) -> str:
        """Get image digest using docker/podman."""
        try:
            # Try docker first
            result = await self._run_command([
                "docker", "inspect", "--format={{.RepoDigests}}", image
            ])
            
            if result["returncode"] == 0:
                digests = result["stdout"].strip()
                if digests and digests != "[]":
                    # Extract digest from [registry/image@sha256:...]
                    digest_match = re.search(r'sha256:[a-f0-9]{64}', digests)
                    if digest_match:
                        return digest_match.group(0)
            
            # Try podman as fallback
            result = await self._run_command([
                "podman", "inspect", "--format={{.RepoDigests}}", image
            ])
            
            if result["returncode"] == 0:
                digests = result["stdout"].strip()
                if digests and digests != "[]":
                    digest_match = re.search(r'sha256:[a-f0-9]{64}', digests)
                    if digest_match:
                        return digest_match.group(0)
            
            # Fallback: generate digest from image name
            return "sha256:" + hashlib.sha256(image.encode()).hexdigest()

        except Exception as e:
            logger.warning(f"Failed to get image digest for {image}: {e}")
            return "sha256:" + hashlib.sha256(image.encode()).hexdigest()

    async def _run_command(self, cmd: List[str]) -> Dict[str, Any]:
        """Run a command asynchronously."""
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            return {
                "returncode": process.returncode,
                "stdout": stdout.decode("utf-8", errors="replace"),
                "stderr": stderr.decode("utf-8", errors="replace")
            }
        except Exception as e:
            logger.error(f"Command failed: {' '.join(cmd)}: {e}")
            return {"returncode": -1, "stdout": "", "stderr": str(e)}

    async def _apply_verification_policy(
        self, 
        result: VerificationResult, 
        policy_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Apply verification policy to result."""
        from .policy import VerificationPolicy
        
        try:
            policy = VerificationPolicy(policy_config)
            return await policy.evaluate(result)
        except Exception as e:
            logger.error(f"Policy evaluation failed: {e}")
            return {
                "allowed": False,
                "violations": [f"Policy evaluation error: {e}"]
            }

    async def verify_image_batch(
        self,
        images: List[str],
        verification_config: Optional[Dict[str, Any]] = None
    ) -> List[VerificationResult]:
        """Verify multiple images in parallel."""
        tasks = [
            self.verify_image(image, verification_config)
            for image in images
        ]
        
        return await asyncio.gather(*tasks, return_exceptions=False)

    def get_verification_summary(self, results: List[VerificationResult]) -> Dict[str, Any]:
        """Get summary of verification results."""
        total = len(results)
        verified = sum(1 for r in results if r.verified)
        failed = sum(1 for r in results if r.status == VerificationStatus.FAILED)
        skipped = sum(1 for r in results if r.status == VerificationStatus.SKIPPED)
        
        return {
            "total": total,
            "verified": verified,
            "failed": failed,
            "skipped": skipped,
            "success_rate": (verified / total * 100) if total > 0 else 0,
            "details": [r.to_dict() for r in results]
        }

    async def get_image_vulnerabilities(self, image: str) -> Dict[str, Any]:
        """Get vulnerability information for an image."""
        try:
            # Try trivy first
            result = await self._run_command([
                "trivy", "image", "--format", "json", "--quiet", image
            ])
            
            if result["returncode"] == 0:
                try:
                    vuln_data = json.loads(result["stdout"])
                    return self._parse_trivy_output(vuln_data)
                except json.JSONDecodeError:
                    pass
            
            # Try grype as fallback
            result = await self._run_command([
                "grype", image, "-o", "json"
            ])
            
            if result["returncode"] == 0:
                try:
                    vuln_data = json.loads(result["stdout"])
                    return self._parse_grype_output(vuln_data)
                except json.JSONDecodeError:
                    pass
            
            return {
                "scanner": "none",
                "vulnerabilities": [],
                "summary": {"total": 0, "critical": 0, "high": 0, "medium": 0, "low": 0}
            }

        except Exception as e:
            logger.error(f"Vulnerability scan failed for {image}: {e}")
            return {
                "scanner": "error",
                "error": str(e),
                "vulnerabilities": [],
                "summary": {"total": 0, "critical": 0, "high": 0, "medium": 0, "low": 0}
            }

    def _parse_trivy_output(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Trivy vulnerability output."""
        vulns = []
        summary = {"total": 0, "critical": 0, "high": 0, "medium": 0, "low": 0}
        
        for result in data.get("Results", []):
            for vuln in result.get("Vulnerabilities", []):
                severity = vuln.get("Severity", "").lower()
                vulns.append({
                    "id": vuln.get("VulnerabilityID"),
                    "severity": severity,
                    "title": vuln.get("Title"),
                    "description": vuln.get("Description"),
                    "package": vuln.get("PkgName"),
                    "installed_version": vuln.get("InstalledVersion"),
                    "fixed_version": vuln.get("FixedVersion"),
                    "references": vuln.get("References", [])
                })
                
                if severity in summary:
                    summary[severity] += 1
                summary["total"] += 1
        
        return {
            "scanner": "trivy",
            "vulnerabilities": vulns,
            "summary": summary
        }

    def _parse_grype_output(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Grype vulnerability output."""
        vulns = []
        summary = {"total": 0, "critical": 0, "high": 0, "medium": 0, "low": 0}
        
        for match in data.get("matches", []):
            vuln = match.get("vulnerability", {})
            artifact = match.get("artifact", {})
            
            severity = vuln.get("severity", "").lower()
            vulns.append({
                "id": vuln.get("id"),
                "severity": severity,
                "title": vuln.get("summary"),
                "description": vuln.get("description"),
                "package": artifact.get("name"),
                "installed_version": artifact.get("version"),
                "fixed_version": match.get("relatedVulnerabilities", [{}])[0].get("fixedInVersion"),
                "references": vuln.get("urls", [])
            })
            
            if severity in summary:
                summary[severity] += 1
            summary["total"] += 1
        
        return {
            "scanner": "grype",
            "vulnerabilities": vulns,
            "summary": summary
        }