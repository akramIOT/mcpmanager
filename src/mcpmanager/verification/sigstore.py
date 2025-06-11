"""Sigstore-based image verification."""

import asyncio
import json
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

from .verifier import SignatureInfo, AttestationInfo

logger = logging.getLogger(__name__)


class SigstoreVerifier:
    """Sigstore-based image verification using cosign."""

    def __init__(self):
        """Initialize Sigstore verifier."""
        self.cosign_available = None

    async def is_available(self) -> bool:
        """Check if cosign is available."""
        if self.cosign_available is None:
            try:
                result = await self._run_command(["cosign", "version"])
                self.cosign_available = result["returncode"] == 0
            except Exception:
                self.cosign_available = False
        
        return self.cosign_available

    async def verify(
        self,
        image: str,
        digest: str,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Verify image using Sigstore/cosign."""
        if not await self.is_available():
            raise Exception("cosign not available for Sigstore verification")

        result = {
            "verified": False,
            "signatures": [],
            "attestations": [],
            "violations": []
        }

        try:
            # Verify signatures
            if config.get("verify_signatures", True):
                sig_result = await self._verify_signatures(image, config)
                result["signatures"] = sig_result["signatures"]
                if not sig_result["verified"]:
                    result["violations"].extend(sig_result["violations"])

            # Verify attestations
            if config.get("verify_attestations", False):
                att_result = await self._verify_attestations(image, config)
                result["attestations"] = att_result["attestations"]
                if not att_result["verified"]:
                    result["violations"].extend(att_result["violations"])

            # Overall verification status
            result["verified"] = (
                len(result["violations"]) == 0 and
                (len(result["signatures"]) > 0 or config.get("allow_unsigned", False))
            )

        except Exception as e:
            logger.error(f"Sigstore verification failed for {image}: {e}")
            result["violations"].append(f"Verification error: {e}")

        return result

    async def _verify_signatures(
        self,
        image: str,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Verify image signatures."""
        result = {
            "verified": False,
            "signatures": [],
            "violations": []
        }

        try:
            # Build cosign verify command
            cmd = ["cosign", "verify"]
            
            # Add key or keyless verification
            public_key = config.get("public_key")
            if public_key:
                if public_key.startswith("http"):
                    cmd.extend(["--key", public_key])
                else:
                    # Write key to temp file
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.pub', delete=False) as f:
                        f.write(public_key)
                        cmd.extend(["--key", f.name])
            else:
                # Keyless verification
                cmd.append("--certificate-identity-regexp")
                cmd.append(config.get("identity_regexp", ".*"))
                cmd.append("--certificate-oidc-issuer-regexp")
                cmd.append(config.get("issuer_regexp", ".*"))

            # Add other options
            if config.get("rekor_url"):
                cmd.extend(["--rekor-url", config["rekor_url"]])
            
            cmd.extend(["-o", "json", image])

            # Run verification
            verify_result = await self._run_command(cmd)

            if verify_result["returncode"] == 0:
                # Parse signatures
                try:
                    signatures_data = json.loads(verify_result["stdout"])
                    for sig_data in signatures_data:
                        sig_info = SignatureInfo(
                            keyid=sig_data.get("optional", {}).get("keyid", ""),
                            signature=sig_data.get("signature", ""),
                            algorithm="sha256",  # Default
                            timestamp=self._parse_timestamp(sig_data.get("optional", {}).get("timestamp")),
                            issuer=sig_data.get("optional", {}).get("Issuer"),
                            subject=sig_data.get("optional", {}).get("Subject")
                        )
                        result["signatures"].append(sig_info)
                    
                    result["verified"] = len(result["signatures"]) > 0

                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse cosign output: {e}")
                    result["violations"].append("Invalid signature verification output")
            else:
                error_msg = verify_result["stderr"].strip()
                if "no matching signatures" in error_msg.lower():
                    result["violations"].append("No valid signatures found")
                else:
                    result["violations"].append(f"Signature verification failed: {error_msg}")

        except Exception as e:
            logger.error(f"Signature verification failed: {e}")
            result["violations"].append(f"Signature verification error: {e}")

        return result

    async def _verify_attestations(
        self,
        image: str,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Verify image attestations."""
        result = {
            "verified": False,
            "attestations": [],
            "violations": []
        }

        try:
            attestation_types = config.get("attestation_types", ["slsa-provenance"])
            
            for att_type in attestation_types:
                att_result = await self._verify_attestation_type(image, att_type, config)
                result["attestations"].extend(att_result["attestations"])
                if att_result["violations"]:
                    result["violations"].extend(att_result["violations"])

            # Consider attestations verified if we have at least one valid attestation
            # and no violations (unless allow_missing_attestations is true)
            if config.get("allow_missing_attestations", True):
                result["verified"] = len(result["violations"]) == 0
            else:
                result["verified"] = len(result["attestations"]) > 0 and len(result["violations"]) == 0

        except Exception as e:
            logger.error(f"Attestation verification failed: {e}")
            result["violations"].append(f"Attestation verification error: {e}")

        return result

    async def _verify_attestation_type(
        self,
        image: str,
        attestation_type: str,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Verify a specific attestation type."""
        result = {
            "attestations": [],
            "violations": []
        }

        try:
            # Build cosign verify-attestation command
            cmd = ["cosign", "verify-attestation"]
            
            # Add key or keyless verification (same as signatures)
            public_key = config.get("public_key")
            if public_key:
                if public_key.startswith("http"):
                    cmd.extend(["--key", public_key])
                else:
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.pub', delete=False) as f:
                        f.write(public_key)
                        cmd.extend(["--key", f.name])
            else:
                cmd.append("--certificate-identity-regexp")
                cmd.append(config.get("identity_regexp", ".*"))
                cmd.append("--certificate-oidc-issuer-regexp")
                cmd.append(config.get("issuer_regexp", ".*"))

            # Add attestation type
            cmd.extend(["--type", attestation_type])
            cmd.extend(["-o", "json", image])

            # Run verification
            verify_result = await self._run_command(cmd)

            if verify_result["returncode"] == 0:
                try:
                    attestations_data = json.loads(verify_result["stdout"])
                    for att_data in attestations_data:
                        payload = att_data.get("payload", {})
                        if isinstance(payload, str):
                            import base64
                            payload = json.loads(base64.b64decode(payload))

                        att_info = AttestationInfo(
                            type=attestation_type,
                            payload=payload,
                            verified=True,
                            timestamp=self._parse_timestamp(att_data.get("optional", {}).get("timestamp"))
                        )
                        result["attestations"].append(att_info)

                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse attestation output: {e}")
                    result["violations"].append(f"Invalid {attestation_type} attestation output")
            else:
                error_msg = verify_result["stderr"].strip()
                if "no matching attestations" not in error_msg.lower():
                    result["violations"].append(f"{attestation_type} attestation verification failed: {error_msg}")

        except Exception as e:
            logger.error(f"Attestation verification failed for {attestation_type}: {e}")
            result["violations"].append(f"{attestation_type} attestation error: {e}")

        return result

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

    def _parse_timestamp(self, timestamp_str: Optional[str]) -> Optional[datetime]:
        """Parse timestamp string."""
        if not timestamp_str:
            return None
        
        try:
            # Try different timestamp formats
            for fmt in [
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S.%fZ", 
                "%Y-%m-%dT%H:%M:%S%z"
            ]:
                try:
                    return datetime.strptime(timestamp_str, fmt).replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
            
            # Fallback to ISO format
            return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            
        except Exception as e:
            logger.warning(f"Failed to parse timestamp '{timestamp_str}': {e}")
            return None