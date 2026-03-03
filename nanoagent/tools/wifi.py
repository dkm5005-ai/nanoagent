"""WiFi network analysis tools"""

import subprocess
from .base import Tool, ToolResult


class WifiStatusTool(Tool):
    """Get current WiFi connection status"""

    @property
    def name(self) -> str:
        return "wifi_status"

    @property
    def description(self) -> str:
        return "Get current WiFi connection status including SSID, signal strength, IP address"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(self, **kwargs) -> ToolResult:
        try:
            # Get connection info
            result = subprocess.run(
                ["iwconfig", "wlan0"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            iwconfig = result.stdout + result.stderr

            # Get IP address
            result = subprocess.run(
                ["hostname", "-I"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            ip = result.stdout.strip()

            output = f"IP: {ip}\n{iwconfig}"
            return ToolResult(content=output)
        except Exception as e:
            return ToolResult(content=f"Error: {e}", is_error=True)


class WifiScanTool(Tool):
    """Scan for available WiFi networks"""

    @property
    def name(self) -> str:
        return "wifi_scan"

    @property
    def description(self) -> str:
        return "Scan for available WiFi networks and list them with signal strength"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(self, **kwargs) -> ToolResult:
        try:
            # Use nmcli for cleaner output
            result = subprocess.run(
                ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "dev", "wifi", "list"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                # Fallback to iwlist
                result = subprocess.run(
                    ["sudo", "iwlist", "wlan0", "scan"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

            output = result.stdout or result.stderr
            return ToolResult(content=output[:2000])  # Limit output size
        except Exception as e:
            return ToolResult(content=f"Error: {e}", is_error=True)


class WifiSpeedTestTool(Tool):
    """Test network speed with a quick ping test"""

    @property
    def name(self) -> str:
        return "wifi_ping"

    @property
    def description(self) -> str:
        return "Test network latency by pinging a host (default: google.com)"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "host": {
                    "type": "string",
                    "description": "Host to ping (default: google.com)",
                },
                "count": {
                    "type": "integer",
                    "description": "Number of pings (default: 4)",
                },
            },
            "required": [],
        }

    async def execute(self, host: str = "google.com", count: int = 4, **kwargs) -> ToolResult:
        try:
            result = subprocess.run(
                ["ping", "-c", str(min(count, 10)), host],
                capture_output=True,
                text=True,
                timeout=30,
            )
            output = result.stdout or result.stderr
            return ToolResult(content=output)
        except Exception as e:
            return ToolResult(content=f"Error: {e}", is_error=True)
