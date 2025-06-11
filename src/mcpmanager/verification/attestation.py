"""Attestation verification and processing."""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)


class AttestationType(str, Enum):
    """Supported attestation types."""
    SLSA_PROVENANCE = "slsa-provenance"
    SLSA_PROVENANCE_V1 = "slsa-provenance-v1"
    SPDX = "spdx"
    CYCLONE_DX = "cyclone-dx"
    SARIF = "sarif"
    VULN_SCAN = "vuln-scan"
    CUSTOM = "custom"


class AttestationVerifier:
    """Verifier for different attestation types."""

    def __init__(self):
        """Initialize attestation verifier."""
        self.processors = {
            AttestationType.SLSA_PROVENANCE: self._process_slsa_provenance,
            AttestationType.SLSA_PROVENANCE_V1: self._process_slsa_provenance_v1,
            AttestationType.SPDX: self._process_spdx,
            AttestationType.CYCLONE_DX: self._process_cyclone_dx,
            AttestationType.SARIF: self._process_sarif,
            AttestationType.VULN_SCAN: self._process_vuln_scan,
        }

    async def verify_attestation(
        self,
        attestation_data: Dict[str, Any],
        attestation_type: str,
        requirements: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Verify and process an attestation."""
        try:
            # Get processor for this attestation type
            att_type = AttestationType(attestation_type) if attestation_type in [e.value for e in AttestationType] else AttestationType.CUSTOM
            processor = self.processors.get(att_type, self._process_custom)

            # Process the attestation
            processed = await processor(attestation_data)

            # Apply requirements if specified
            violations = []
            if requirements:
                violations = await self._check_requirements(processed, requirements, att_type)

            return {
                "type": attestation_type,
                "verified": len(violations) == 0,
                "violations": violations,
                "processed_data": processed,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        except Exception as e:
            logger.error(f"Attestation verification failed: {e}")
            return {
                "type": attestation_type,
                "verified": False,
                "violations": [f"Processing error: {e}"],
                "processed_data": {},
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    async def _process_slsa_provenance(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process SLSA provenance attestation."""
        try:
            predicate = data.get("predicate", {})
            builder = predicate.get("builder", {})
            build_definition = predicate.get("buildDefinition", {})
            run_details = predicate.get("runDetails", {})

            return {
                "builder_id": builder.get("id"),
                "builder_version": builder.get("version"),
                "build_type": build_definition.get("buildType"),
                "external_parameters": build_definition.get("externalParameters", {}),
                "resolved_dependencies": build_definition.get("resolvedDependencies", []),
                "build_start_time": run_details.get("builder", {}).get("builderStartedOn"),
                "build_finish_time": run_details.get("builder", {}).get("builderFinishedOn"),
                "metadata": predicate.get("metadata", {}),
                "materials": predicate.get("materials", [])
            }
        except Exception as e:
            logger.error(f"Failed to process SLSA provenance: {e}")
            return {"error": str(e)}

    async def _process_slsa_provenance_v1(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process SLSA provenance v1.0 attestation."""
        try:
            predicate = data.get("predicate", {})
            build_definition = predicate.get("buildDefinition", {})
            run_details = predicate.get("runDetails", {})

            return {
                "build_type": build_definition.get("buildType"),
                "external_parameters": build_definition.get("externalParameters", {}),
                "internal_parameters": build_definition.get("internalParameters", {}),
                "resolved_dependencies": build_definition.get("resolvedDependencies", []),
                "builder": run_details.get("builder", {}),
                "metadata": run_details.get("metadata", {}),
                "byproducts": run_details.get("byproducts", [])
            }
        except Exception as e:
            logger.error(f"Failed to process SLSA provenance v1: {e}")
            return {"error": str(e)}

    async def _process_spdx(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process SPDX SBOM attestation."""
        try:
            predicate = data.get("predicate", {})
            
            return {
                "spdx_version": predicate.get("spdxVersion"),
                "spdx_id": predicate.get("SPDXID"),
                "name": predicate.get("name"),
                "document_namespace": predicate.get("documentNamespace"),
                "creators": predicate.get("creationInfo", {}).get("creators", []),
                "created": predicate.get("creationInfo", {}).get("created"),
                "packages": predicate.get("packages", []),
                "relationships": predicate.get("relationships", []),
                "package_count": len(predicate.get("packages", [])),
                "relationship_count": len(predicate.get("relationships", []))
            }
        except Exception as e:
            logger.error(f"Failed to process SPDX: {e}")
            return {"error": str(e)}

    async def _process_cyclone_dx(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process CycloneDX SBOM attestation."""
        try:
            predicate = data.get("predicate", {})
            
            return {
                "spec_version": predicate.get("specVersion"),
                "version": predicate.get("version"),
                "serial_number": predicate.get("serialNumber"),
                "metadata": predicate.get("metadata", {}),
                "components": predicate.get("components", []),
                "services": predicate.get("services", []),
                "dependencies": predicate.get("dependencies", []),
                "vulnerabilities": predicate.get("vulnerabilities", []),
                "component_count": len(predicate.get("components", [])),
                "vulnerability_count": len(predicate.get("vulnerabilities", []))
            }
        except Exception as e:
            logger.error(f"Failed to process CycloneDX: {e}")
            return {"error": str(e)}

    async def _process_sarif(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process SARIF security scan results."""
        try:
            predicate = data.get("predicate", {})
            runs = predicate.get("runs", [])
            
            total_results = 0
            tools = []
            
            for run in runs:
                tool_info = run.get("tool", {}).get("driver", {})
                tools.append({
                    "name": tool_info.get("name"),
                    "version": tool_info.get("version"),
                    "semantic_version": tool_info.get("semanticVersion")
                })
                
                results = run.get("results", [])
                total_results += len(results)

            return {
                "schema_version": predicate.get("$schema"),
                "version": predicate.get("version"),
                "runs_count": len(runs),
                "tools": tools,
                "total_results": total_results,
                "runs": runs
            }
        except Exception as e:
            logger.error(f"Failed to process SARIF: {e}")
            return {"error": str(e)}

    async def _process_vuln_scan(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process vulnerability scan attestation."""
        try:
            predicate = data.get("predicate", {})
            scanner = predicate.get("scanner", {})
            metadata = predicate.get("metadata", {})
            
            return {
                "scanner_name": scanner.get("name"),
                "scanner_version": scanner.get("version"),
                "scan_started": metadata.get("scanStartedOn"),
                "scan_finished": metadata.get("scanFinishedOn"),
                "vulnerabilities": predicate.get("vulnerabilities", []),
                "vulnerability_count": len(predicate.get("vulnerabilities", [])),
                "summary": self._summarize_vulnerabilities(predicate.get("vulnerabilities", []))
            }
        except Exception as e:
            logger.error(f"Failed to process vulnerability scan: {e}")
            return {"error": str(e)}

    async def _process_custom(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process custom attestation."""
        try:
            predicate = data.get("predicate", {})
            return {
                "predicate_type": data.get("predicateType"),
                "predicate": predicate,
                "subject": data.get("subject", []),
                "custom_processing": True
            }
        except Exception as e:
            logger.error(f"Failed to process custom attestation: {e}")
            return {"error": str(e)}

    def _summarize_vulnerabilities(self, vulnerabilities: List[Dict[str, Any]]) -> Dict[str, int]:
        """Summarize vulnerability counts by severity."""
        summary = {"critical": 0, "high": 0, "medium": 0, "low": 0, "unknown": 0}
        
        for vuln in vulnerabilities:
            severity = vuln.get("severity", "unknown").lower()
            if severity in summary:
                summary[severity] += 1
            else:
                summary["unknown"] += 1
        
        summary["total"] = len(vulnerabilities)
        return summary

    async def _check_requirements(
        self,
        processed_data: Dict[str, Any],
        requirements: Dict[str, Any],
        attestation_type: AttestationType
    ) -> List[str]:
        """Check attestation against requirements."""
        violations = []

        try:
            # Common requirements
            if "required_fields" in requirements:
                for field in requirements["required_fields"]:
                    if field not in processed_data or processed_data[field] is None:
                        violations.append(f"Required field missing: {field}")

            # Type-specific requirements
            if attestation_type == AttestationType.SLSA_PROVENANCE:
                violations.extend(await self._check_slsa_requirements(processed_data, requirements))
            elif attestation_type == AttestationType.SPDX:
                violations.extend(await self._check_spdx_requirements(processed_data, requirements))
            elif attestation_type == AttestationType.VULN_SCAN:
                violations.extend(await self._check_vuln_requirements(processed_data, requirements))

        except Exception as e:
            logger.error(f"Requirements checking failed: {e}")
            violations.append(f"Requirements check error: {e}")

        return violations

    async def _check_slsa_requirements(
        self,
        data: Dict[str, Any],
        requirements: Dict[str, Any]
    ) -> List[str]:
        """Check SLSA-specific requirements."""
        violations = []

        # Builder requirements
        if "allowed_builders" in requirements:
            builder_id = data.get("builder_id")
            if builder_id not in requirements["allowed_builders"]:
                violations.append(f"Builder not allowed: {builder_id}")

        # Build type requirements
        if "allowed_build_types" in requirements:
            build_type = data.get("build_type")
            if build_type not in requirements["allowed_build_types"]:
                violations.append(f"Build type not allowed: {build_type}")

        # Material requirements
        if "require_materials" in requirements and requirements["require_materials"]:
            materials = data.get("materials", [])
            if not materials:
                violations.append("No build materials found (required)")

        return violations

    async def _check_spdx_requirements(
        self,
        data: Dict[str, Any],
        requirements: Dict[str, Any]
    ) -> List[str]:
        """Check SPDX-specific requirements."""
        violations = []

        # Minimum package count
        if "min_packages" in requirements:
            package_count = data.get("package_count", 0)
            if package_count < requirements["min_packages"]:
                violations.append(f"Too few packages: {package_count} < {requirements['min_packages']}")

        # Required SPDX version
        if "required_spdx_version" in requirements:
            spdx_version = data.get("spdx_version")
            if spdx_version != requirements["required_spdx_version"]:
                violations.append(f"SPDX version mismatch: {spdx_version} != {requirements['required_spdx_version']}")

        return violations

    async def _check_vuln_requirements(
        self,
        data: Dict[str, Any],
        requirements: Dict[str, Any]
    ) -> List[str]:
        """Check vulnerability scan requirements."""
        violations = []

        summary = data.get("summary", {})

        # Maximum vulnerability counts
        if "max_critical" in requirements:
            if summary.get("critical", 0) > requirements["max_critical"]:
                violations.append(f"Too many critical vulnerabilities: {summary['critical']} > {requirements['max_critical']}")

        if "max_high" in requirements:
            if summary.get("high", 0) > requirements["max_high"]:
                violations.append(f"Too many high vulnerabilities: {summary['high']} > {requirements['max_high']}")

        if "max_total" in requirements:
            if summary.get("total", 0) > requirements["max_total"]:
                violations.append(f"Too many total vulnerabilities: {summary['total']} > {requirements['max_total']}")

        # Required scanner
        if "allowed_scanners" in requirements:
            scanner = data.get("scanner_name")
            if scanner not in requirements["allowed_scanners"]:
                violations.append(f"Scanner not allowed: {scanner}")

        return violations

    def get_supported_types(self) -> List[str]:
        """Get list of supported attestation types."""
        return [att_type.value for att_type in AttestationType]

    async def extract_attestation_metadata(self, attestation_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract metadata from attestation for indexing/searching."""
        metadata = {}

        try:
            # Common metadata
            metadata["predicate_type"] = attestation_data.get("predicateType")
            metadata["subject"] = attestation_data.get("subject", [])
            
            # Extract timestamps
            predicate = attestation_data.get("predicate", {})
            
            # Look for various timestamp fields
            timestamp_fields = [
                "timestamp", "created", "scanStartedOn", "builderStartedOn",
                "metadata.scanStartedOn", "creationInfo.created"
            ]
            
            for field in timestamp_fields:
                value = self._get_nested_value(predicate, field)
                if value:
                    metadata["timestamp"] = value
                    break

            # Extract tool/scanner information
            tool_fields = [
                "scanner.name", "tool.driver.name", "builder.id"
            ]
            
            for field in tool_fields:
                value = self._get_nested_value(predicate, field)
                if value:
                    metadata["tool"] = value
                    break

        except Exception as e:
            logger.error(f"Failed to extract attestation metadata: {e}")

        return metadata

    def _get_nested_value(self, data: Dict[str, Any], path: str) -> Any:
        """Get nested value from dict using dot notation."""
        try:
            keys = path.split('.')
            value = data
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return None