"""Inspector and debugging tools for MCP servers."""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path

import psutil
import aiofiles

from mcpmanager.exceptions import MCPManagerError

logger = logging.getLogger(__name__)


class InspectorError(MCPManagerError):
    """Inspector-related error."""
    pass


@dataclass
class ContainerMetrics:
    """Container performance metrics."""
    container_id: str
    cpu_percent: float
    memory_usage_mb: float
    memory_percent: float
    network_io_read_mb: float
    network_io_write_mb: float
    disk_io_read_mb: float
    disk_io_write_mb: float
    timestamp: datetime
    uptime_seconds: float


@dataclass
class MCPServerDebugInfo:
    """Debug information for an MCP server."""
    name: str
    container_id: str
    status: str
    image: str
    ports: List[Dict[str, Any]]
    environment: Dict[str, str]
    labels: Dict[str, str]
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    exit_code: Optional[int]
    restart_count: int
    network_settings: Dict[str, Any]
    mounts: List[Dict[str, Any]]


@dataclass
class LogEntry:
    """Log entry with metadata."""
    timestamp: datetime
    level: str
    message: str
    source: str
    container_id: str


class MCPInspector:
    """Inspector for debugging MCP servers."""

    def __init__(self, docker_client, manager):
        """Initialize inspector."""
        self.docker_client = docker_client
        self.manager = manager
        self._metrics_history: Dict[str, List[ContainerMetrics]] = {}
        self._max_history_entries = 1000

    async def get_server_debug_info(self, server_name: str) -> MCPServerDebugInfo:
        """Get comprehensive debug information for a server."""
        # Get server instance
        instance = await self.manager.get_server_status(server_name)
        if not instance:
            raise InspectorError(f"Server {server_name} not found")

        # Get container details
        container_info = await self.docker_client.get_container_info(instance.container_id)
        
        # Get additional container details
        container_details = await self.docker_client.inspect_container(instance.container_id)
        
        debug_info = MCPServerDebugInfo(
            name=server_name,
            container_id=instance.container_id,
            status=container_info.status,
            image=container_info.image,
            ports=[asdict(port) for port in container_info.ports],
            environment=container_details.get("Config", {}).get("Env", {}),
            labels=container_info.labels,
            created_at=container_info.created,
            started_at=self._parse_timestamp(container_details.get("State", {}).get("StartedAt")),
            finished_at=self._parse_timestamp(container_details.get("State", {}).get("FinishedAt")),
            exit_code=container_details.get("State", {}).get("ExitCode"),
            restart_count=container_details.get("RestartCount", 0),
            network_settings=container_details.get("NetworkSettings", {}),
            mounts=container_details.get("Mounts", [])
        )

        return debug_info

    async def collect_metrics(self, server_name: str) -> ContainerMetrics:
        """Collect performance metrics for a server."""
        instance = await self.manager.get_server_status(server_name)
        if not instance:
            raise InspectorError(f"Server {server_name} not found")

        # Get container stats
        stats = await self.docker_client.get_container_stats(instance.container_id)
        
        # Calculate metrics
        cpu_percent = self._calculate_cpu_percent(stats)
        memory_usage_mb = stats.get("memory", {}).get("usage", 0) / (1024 * 1024)
        memory_limit = stats.get("memory", {}).get("limit", 1)
        memory_percent = (stats.get("memory", {}).get("usage", 0) / memory_limit) * 100

        # Network I/O
        networks = stats.get("networks", {})
        network_io_read = sum(net.get("rx_bytes", 0) for net in networks.values()) / (1024 * 1024)
        network_io_write = sum(net.get("tx_bytes", 0) for net in networks.values()) / (1024 * 1024)

        # Disk I/O
        blkio = stats.get("blkio_stats", {}).get("io_service_bytes_recursive", [])
        disk_io_read = sum(item.get("value", 0) for item in blkio if item.get("op") == "Read") / (1024 * 1024)
        disk_io_write = sum(item.get("value", 0) for item in blkio if item.get("op") == "Write") / (1024 * 1024)

        # Uptime
        started_at = stats.get("read")
        uptime_seconds = 0
        if started_at:
            uptime_seconds = (datetime.now() - datetime.fromisoformat(started_at.replace('Z', '+00:00'))).total_seconds()

        metrics = ContainerMetrics(
            container_id=instance.container_id,
            cpu_percent=cpu_percent,
            memory_usage_mb=memory_usage_mb,
            memory_percent=memory_percent,
            network_io_read_mb=network_io_read,
            network_io_write_mb=network_io_write,
            disk_io_read_mb=disk_io_read,
            disk_io_write_mb=disk_io_write,
            timestamp=datetime.now(),
            uptime_seconds=uptime_seconds
        )

        # Store in history
        if server_name not in self._metrics_history:
            self._metrics_history[server_name] = []
        
        self._metrics_history[server_name].append(metrics)
        
        # Limit history size
        if len(self._metrics_history[server_name]) > self._max_history_entries:
            self._metrics_history[server_name] = self._metrics_history[server_name][-self._max_history_entries:]

        return metrics

    async def get_metrics_history(
        self, 
        server_name: str, 
        duration_minutes: int = 60
    ) -> List[ContainerMetrics]:
        """Get metrics history for a server."""
        if server_name not in self._metrics_history:
            return []

        cutoff_time = datetime.now() - timedelta(minutes=duration_minutes)
        return [
            metric for metric in self._metrics_history[server_name]
            if metric.timestamp >= cutoff_time
        ]

    async def analyze_performance(self, server_name: str) -> Dict[str, Any]:
        """Analyze server performance and provide insights."""
        metrics_history = await self.get_metrics_history(server_name, 30)  # Last 30 minutes
        
        if not metrics_history:
            return {"status": "no_data", "message": "No metrics available"}

        # Calculate averages
        avg_cpu = sum(m.cpu_percent for m in metrics_history) / len(metrics_history)
        avg_memory = sum(m.memory_usage_mb for m in metrics_history) / len(metrics_history)
        avg_memory_percent = sum(m.memory_percent for m in metrics_history) / len(metrics_history)

        # Detect anomalies
        anomalies = []
        
        # High CPU usage
        if avg_cpu > 80:
            anomalies.append({
                "type": "high_cpu",
                "severity": "warning",
                "message": f"High average CPU usage: {avg_cpu:.1f}%"
            })

        # High memory usage
        if avg_memory_percent > 80:
            anomalies.append({
                "type": "high_memory",
                "severity": "warning", 
                "message": f"High memory usage: {avg_memory_percent:.1f}%"
            })

        # Memory leaks (increasing trend)
        if len(metrics_history) >= 10:
            recent_memory = [m.memory_usage_mb for m in metrics_history[-10:]]
            if self._is_increasing_trend(recent_memory):
                anomalies.append({
                    "type": "memory_leak",
                    "severity": "error",
                    "message": "Possible memory leak detected (increasing memory usage trend)"
                })

        # CPU spikes
        cpu_values = [m.cpu_percent for m in metrics_history]
        if max(cpu_values) - min(cpu_values) > 50:
            anomalies.append({
                "type": "cpu_spikes",
                "severity": "info",
                "message": "High CPU usage variability detected"
            })

        return {
            "status": "analyzed",
            "metrics_count": len(metrics_history),
            "averages": {
                "cpu_percent": round(avg_cpu, 2),
                "memory_usage_mb": round(avg_memory, 2),
                "memory_percent": round(avg_memory_percent, 2)
            },
            "anomalies": anomalies,
            "recommendations": self._generate_recommendations(anomalies)
        }

    async def trace_mcp_communication(self, server_name: str, duration_seconds: int = 60) -> List[Dict[str, Any]]:
        """Trace MCP communication for debugging."""
        instance = await self.manager.get_server_status(server_name)
        if not instance:
            raise InspectorError(f"Server {server_name} not found")

        # This is a simplified implementation
        # In a real scenario, you'd need to hook into the transport layer
        trace_data = []
        
        start_time = time.time()
        while time.time() - start_time < duration_seconds:
            # Get recent logs that might contain MCP communication
            logs = await self.manager.get_server_logs(server_name, tail=10)
            
            # Parse logs for MCP-related entries
            for line in logs.split('\n'):
                if any(keyword in line.lower() for keyword in ['mcp', 'json-rpc', 'method', 'params']):
                    trace_data.append({
                        "timestamp": datetime.now().isoformat(),
                        "type": "log_entry",
                        "content": line.strip(),
                        "source": "container_logs"
                    })
            
            await asyncio.sleep(1)

        return trace_data

    async def generate_debug_report(self, server_name: str) -> Dict[str, Any]:
        """Generate comprehensive debug report."""
        try:
            # Collect all debug information
            debug_info = await self.get_server_debug_info(server_name)
            current_metrics = await self.collect_metrics(server_name)
            performance_analysis = await self.analyze_performance(server_name)
            recent_logs = await self.manager.get_server_logs(server_name, tail=100)

            report = {
                "server_name": server_name,
                "generated_at": datetime.now().isoformat(),
                "debug_info": asdict(debug_info),
                "current_metrics": asdict(current_metrics),
                "performance_analysis": performance_analysis,
                "recent_logs": recent_logs.split('\n')[-50:],  # Last 50 log lines
                "system_info": await self._get_system_info()
            }

            return report

        except Exception as e:
            logger.error(f"Failed to generate debug report for {server_name}: {e}")
            raise InspectorError(f"Failed to generate debug report: {e}")

    async def export_debug_report(self, server_name: str, output_path: str) -> str:
        """Export debug report to file."""
        report = await self.generate_debug_report(server_name)
        
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        async with aiofiles.open(output_file, 'w') as f:
            await f.write(json.dumps(report, indent=2, default=str))
        
        logger.info(f"Debug report exported to {output_file}")
        return str(output_file)

    def _calculate_cpu_percent(self, stats: Dict[str, Any]) -> float:
        """Calculate CPU percentage from container stats."""
        cpu_stats = stats.get("cpu_stats", {})
        precpu_stats = stats.get("precpu_stats", {})
        
        if not cpu_stats or not precpu_stats:
            return 0.0

        cpu_usage = cpu_stats.get("cpu_usage", {}).get("total_usage", 0)
        precpu_usage = precpu_stats.get("cpu_usage", {}).get("total_usage", 0)
        
        system_usage = cpu_stats.get("system_cpu_usage", 0)
        presystem_usage = precpu_stats.get("system_cpu_usage", 0)
        
        online_cpus = cpu_stats.get("online_cpus", 1)
        
        cpu_delta = cpu_usage - precpu_usage
        system_delta = system_usage - presystem_usage
        
        if system_delta > 0:
            return (cpu_delta / system_delta) * online_cpus * 100
        
        return 0.0

    def _parse_timestamp(self, timestamp_str: Optional[str]) -> Optional[datetime]:
        """Parse timestamp string to datetime."""
        if not timestamp_str or timestamp_str == "0001-01-01T00:00:00Z":
            return None
        
        try:
            return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        except Exception:
            return None

    def _is_increasing_trend(self, values: List[float]) -> bool:
        """Check if values show an increasing trend."""
        if len(values) < 3:
            return False
        
        increases = 0
        for i in range(1, len(values)):
            if values[i] > values[i-1]:
                increases += 1
        
        return increases / (len(values) - 1) > 0.7  # 70% of values are increasing

    def _generate_recommendations(self, anomalies: List[Dict[str, Any]]) -> List[str]:
        """Generate recommendations based on anomalies."""
        recommendations = []
        
        for anomaly in anomalies:
            if anomaly["type"] == "high_cpu":
                recommendations.append("Consider scaling the server or optimizing CPU-intensive operations")
            elif anomaly["type"] == "high_memory":
                recommendations.append("Consider increasing memory limits or optimizing memory usage")
            elif anomaly["type"] == "memory_leak":
                recommendations.append("Investigate potential memory leaks and consider restarting the server")
            elif anomaly["type"] == "cpu_spikes":
                recommendations.append("Monitor for irregular workload patterns or resource contention")
        
        if not recommendations:
            recommendations.append("Server performance appears normal")
        
        return recommendations

    async def _get_system_info(self) -> Dict[str, Any]:
        """Get system information."""
        try:
            return {
                "cpu_count": psutil.cpu_count(),
                "memory_total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
                "memory_available_gb": round(psutil.virtual_memory().available / (1024**3), 2),
                "disk_usage_percent": psutil.disk_usage('/').percent,
                "load_average": psutil.getloadavg() if hasattr(psutil, 'getloadavg') else None
            }
        except Exception as e:
            logger.warning(f"Could not get system info: {e}")
            return {"error": str(e)}


class DebugSession:
    """Interactive debugging session for MCP servers."""

    def __init__(self, inspector: MCPInspector, server_name: str):
        """Initialize debug session."""
        self.inspector = inspector
        self.server_name = server_name
        self.session_id = f"debug-{server_name}-{int(time.time())}"
        self.start_time = datetime.now()
        self.commands_executed = []

    async def execute_command(self, command: str, **kwargs) -> Dict[str, Any]:
        """Execute a debug command."""
        self.commands_executed.append({
            "command": command,
            "timestamp": datetime.now().isoformat(),
            "kwargs": kwargs
        })

        if command == "status":
            return await self._cmd_status()
        elif command == "metrics":
            return await self._cmd_metrics()
        elif command == "logs":
            return await self._cmd_logs(**kwargs)
        elif command == "trace":
            return await self._cmd_trace(**kwargs)
        elif command == "analyze":
            return await self._cmd_analyze()
        elif command == "restart":
            return await self._cmd_restart()
        else:
            return {"error": f"Unknown command: {command}"}

    async def _cmd_status(self) -> Dict[str, Any]:
        """Get server status."""
        debug_info = await self.inspector.get_server_debug_info(self.server_name)
        return {"command": "status", "result": asdict(debug_info)}

    async def _cmd_metrics(self) -> Dict[str, Any]:
        """Get current metrics."""
        metrics = await self.inspector.collect_metrics(self.server_name)
        return {"command": "metrics", "result": asdict(metrics)}

    async def _cmd_logs(self, tail: int = 50, follow: bool = False) -> Dict[str, Any]:
        """Get server logs."""
        logs = await self.inspector.manager.get_server_logs(
            self.server_name, tail=tail, follow=follow
        )
        return {"command": "logs", "result": {"logs": logs.split('\n')}}

    async def _cmd_trace(self, duration: int = 30) -> Dict[str, Any]:
        """Trace MCP communication."""
        trace_data = await self.inspector.trace_mcp_communication(
            self.server_name, duration
        )
        return {"command": "trace", "result": {"trace_data": trace_data}}

    async def _cmd_analyze(self) -> Dict[str, Any]:
        """Analyze performance."""
        analysis = await self.inspector.analyze_performance(self.server_name)
        return {"command": "analyze", "result": analysis}

    async def _cmd_restart(self) -> Dict[str, Any]:
        """Restart server."""
        try:
            instance = await self.inspector.manager.restart_server(self.server_name)
            return {
                "command": "restart", 
                "result": {"status": "success", "new_container_id": instance.container_id}
            }
        except Exception as e:
            return {"command": "restart", "result": {"status": "error", "error": str(e)}}

    def get_session_summary(self) -> Dict[str, Any]:
        """Get session summary."""
        return {
            "session_id": self.session_id,
            "server_name": self.server_name,
            "start_time": self.start_time.isoformat(),
            "duration_seconds": (datetime.now() - self.start_time).total_seconds(),
            "commands_executed": len(self.commands_executed),
            "command_history": self.commands_executed
        }