"""Verification policy engine."""

import logging
import re
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timezone

from .verifier import VerificationResult, VerificationStatus

logger = logging.getLogger(__name__)


class PolicyViolation(Exception):
    """Policy violation error."""
    pass


class VerificationPolicy:
    """Verification policy engine."""

    def __init__(self, policy_config: Dict[str, Any]):
        """Initialize policy."""
        self.config = policy_config
        self.rules = policy_config.get("rules", [])

    async def evaluate(self, result: VerificationResult) -> Dict[str, Any]:
        """Evaluate verification result against policy."""
        violations = []
        allowed = True

        try:
            # Check global policy settings
            global_violations = await self._check_global_policies(result)
            violations.extend(global_violations)

            # Check individual rules
            for rule in self.rules:
                rule_violations = await self._evaluate_rule(result, rule)
                violations.extend(rule_violations)

            # Determine if image is allowed
            if violations:
                enforcement = self.config.get("enforcement", "strict")
                if enforcement == "strict":
                    allowed = False
                elif enforcement == "warn":
                    allowed = True
                    logger.warning(f"Policy violations for {result.image}: {violations}")
                elif enforcement == "log":
                    allowed = True
                    logger.info(f"Policy violations for {result.image}: {violations}")

        except Exception as e:
            logger.error(f"Policy evaluation failed: {e}")
            violations.append(f"Policy evaluation error: {e}")
            allowed = False

        return {
            "allowed": allowed,
            "violations": violations,
            "enforcement": self.config.get("enforcement", "strict")
        }

    async def _check_global_policies(self, result: VerificationResult) -> List[str]:
        """Check global policy requirements."""
        violations = []

        # Require signatures
        if self.config.get("require_signatures", False):
            if not result.signatures:
                violations.append("No signatures found (required by policy)")

        # Require attestations
        if self.config.get("require_attestations", False):
            if not result.attestations:
                violations.append("No attestations found (required by policy)")

        # Require specific attestation types
        required_attestations = self.config.get("required_attestation_types", [])
        if required_attestations:
            found_types = set(att.type for att in result.attestations)
            missing_types = set(required_attestations) - found_types
            if missing_types:
                violations.append(f"Missing required attestation types: {list(missing_types)}")

        # Block unsigned images
        if self.config.get("block_unsigned", False):
            if not result.verified:
                violations.append("Unsigned images are blocked by policy")

        # Check vulnerability policy
        vuln_policy = self.config.get("vulnerability_policy")
        if vuln_policy:
            vuln_violations = await self._check_vulnerability_policy(result, vuln_policy)
            violations.extend(vuln_violations)

        return violations

    async def _evaluate_rule(self, result: VerificationResult, rule: Dict[str, Any]) -> List[str]:
        """Evaluate a single policy rule."""
        violations = []

        try:
            # Check if rule applies to this image
            if not await self._rule_matches(result, rule):
                return []

            # Check rule conditions
            conditions = rule.get("conditions", {})

            # Signature requirements
            if "min_signatures" in conditions:
                min_sigs = conditions["min_signatures"]
                if len(result.signatures) < min_sigs:
                    violations.append(f"Rule '{rule.get('name', 'unnamed')}': Need at least {min_sigs} signatures, got {len(result.signatures)}")

            # Issuer requirements
            if "required_issuers" in conditions:
                required_issuers = conditions["required_issuers"]
                found_issuers = set(sig.issuer for sig in result.signatures if sig.issuer)
                if not any(issuer in found_issuers for issuer in required_issuers):
                    violations.append(f"Rule '{rule.get('name', 'unnamed')}': None of required issuers found: {required_issuers}")

            # Subject requirements
            if "required_subjects" in conditions:
                required_subjects = conditions["required_subjects"]
                found_subjects = set(sig.subject for sig in result.signatures if sig.subject)
                if not any(self._pattern_matches(subject, required_subjects) for subject in found_subjects):
                    violations.append(f"Rule '{rule.get('name', 'unnamed')}': No matching subjects found")

            # Key requirements
            if "required_keys" in conditions:
                required_keys = conditions["required_keys"]
                found_keys = set(sig.keyid for sig in result.signatures if sig.keyid)
                if not any(key in found_keys for key in required_keys):
                    violations.append(f"Rule '{rule.get('name', 'unnamed')}': None of required keys found: {required_keys}")

            # Time-based requirements
            if "max_signature_age_days" in conditions:
                max_age_days = conditions["max_signature_age_days"]
                now = datetime.now(timezone.utc)
                for sig in result.signatures:
                    if sig.timestamp:
                        age_days = (now - sig.timestamp).days
                        if age_days > max_age_days:
                            violations.append(f"Rule '{rule.get('name', 'unnamed')}': Signature too old ({age_days} days > {max_age_days} days)")

        except Exception as e:
            logger.error(f"Rule evaluation failed: {e}")
            violations.append(f"Rule evaluation error: {e}")

        return violations

    async def _rule_matches(self, result: VerificationResult, rule: Dict[str, Any]) -> bool:
        """Check if rule applies to the image."""
        selectors = rule.get("selectors", {})

        # Image name patterns
        image_patterns = selectors.get("images", [])
        if image_patterns:
            if not any(self._pattern_matches(result.image, [pattern]) for pattern in image_patterns):
                return False

        # Registry patterns
        registry_patterns = selectors.get("registries", [])
        if registry_patterns:
            registry = result.image.split('/')[0] if '/' in result.image else result.image
            if not any(self._pattern_matches(registry, [pattern]) for pattern in registry_patterns):
                return False

        # Namespace patterns (for image paths like registry/namespace/image)
        namespace_patterns = selectors.get("namespaces", [])
        if namespace_patterns:
            parts = result.image.split('/')
            if len(parts) >= 3:  # registry/namespace/image
                namespace = parts[1]
                if not any(self._pattern_matches(namespace, [pattern]) for pattern in namespace_patterns):
                    return False

        return True

    def _pattern_matches(self, value: str, patterns: List[str]) -> bool:
        """Check if value matches any of the patterns."""
        for pattern in patterns:
            if self._match_pattern(value, pattern):
                return True
        return False

    def _match_pattern(self, value: str, pattern: str) -> bool:
        """Check if value matches a pattern (supports * and ? wildcards)."""
        # Convert glob pattern to regex
        regex_pattern = pattern.replace('*', '.*').replace('?', '.')
        regex_pattern = f"^{regex_pattern}$"
        
        try:
            return bool(re.match(regex_pattern, value))
        except re.error:
            logger.warning(f"Invalid pattern: {pattern}")
            return False

    async def _check_vulnerability_policy(
        self, 
        result: VerificationResult, 
        vuln_policy: Dict[str, Any]
    ) -> List[str]:
        """Check vulnerability policy requirements."""
        violations = []

        # This would integrate with vulnerability scanning
        # For now, we'll check if vulnerability data is in metadata
        vuln_data = result.metadata.get("vulnerabilities")
        if not vuln_data:
            # If vulnerability scanning is required but no data is available
            if vuln_policy.get("require_scan", False):
                violations.append("Vulnerability scan required but no scan data available")
            return violations

        summary = vuln_data.get("summary", {})
        
        # Check severity limits
        max_critical = vuln_policy.get("max_critical", None)
        if max_critical is not None and summary.get("critical", 0) > max_critical:
            violations.append(f"Too many critical vulnerabilities: {summary['critical']} > {max_critical}")

        max_high = vuln_policy.get("max_high", None)
        if max_high is not None and summary.get("high", 0) > max_high:
            violations.append(f"Too many high vulnerabilities: {summary['high']} > {max_high}")

        max_total = vuln_policy.get("max_total", None)
        if max_total is not None and summary.get("total", 0) > max_total:
            violations.append(f"Too many total vulnerabilities: {summary['total']} > {max_total}")

        # Block specific CVEs
        blocked_cves = vuln_policy.get("blocked_cves", [])
        if blocked_cves:
            found_cves = set(vuln.get("id", "") for vuln in vuln_data.get("vulnerabilities", []))
            blocked_found = set(blocked_cves) & found_cves
            if blocked_found:
                violations.append(f"Blocked CVEs found: {list(blocked_found)}")

        return violations

    def get_policy_summary(self) -> Dict[str, Any]:
        """Get summary of policy configuration."""
        return {
            "enforcement": self.config.get("enforcement", "strict"),
            "require_signatures": self.config.get("require_signatures", False),
            "require_attestations": self.config.get("require_attestations", False),
            "block_unsigned": self.config.get("block_unsigned", False),
            "rules_count": len(self.rules),
            "vulnerability_policy": bool(self.config.get("vulnerability_policy")),
            "required_attestation_types": self.config.get("required_attestation_types", [])
        }


def create_default_policy() -> Dict[str, Any]:
    """Create a default verification policy."""
    return {
        "enforcement": "warn",
        "require_signatures": False,
        "require_attestations": False,
        "block_unsigned": False,
        "rules": [
            {
                "name": "production-images",
                "selectors": {
                    "registries": ["gcr.io", "docker.io", "quay.io"]
                },
                "conditions": {
                    "min_signatures": 1
                }
            }
        ],
        "vulnerability_policy": {
            "require_scan": False,
            "max_critical": 0,
            "max_high": 5,
            "max_total": 50
        }
    }


def create_strict_policy() -> Dict[str, Any]:
    """Create a strict verification policy."""
    return {
        "enforcement": "strict",
        "require_signatures": True,
        "require_attestations": True,
        "block_unsigned": True,
        "required_attestation_types": ["slsa-provenance"],
        "rules": [
            {
                "name": "all-images",
                "selectors": {},
                "conditions": {
                    "min_signatures": 1,
                    "max_signature_age_days": 30
                }
            }
        ],
        "vulnerability_policy": {
            "require_scan": True,
            "max_critical": 0,
            "max_high": 0,
            "max_total": 10
        }
    }