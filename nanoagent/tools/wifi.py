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


class WifiChannelAnalysisTool(Tool):
    """Analyze WiFi channel usage and find congestion"""

    @property
    def name(self) -> str:
        return "wifi_channels"

    @property
    def description(self) -> str:
        return "Analyze WiFi channels to find congestion and overlapping networks"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(self, **kwargs) -> ToolResult:
        try:
            # Scan networks with channel info
            result = subprocess.run(
                ["sudo", "iwlist", "wlan0", "scan"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                return ToolResult(content=f"Scan failed: {result.stderr}", is_error=True)

            # Parse output for channels
            channels_2g = {}  # channel -> list of (ssid, signal)
            channels_5g = {}

            current_ssid = ""
            current_channel = 0
            current_signal = 0
            current_freq = 0

            for line in result.stdout.split('\n'):
                line = line.strip()

                if 'ESSID:' in line:
                    current_ssid = line.split('ESSID:')[1].strip('"')
                elif 'Channel:' in line:
                    try:
                        current_channel = int(line.split('Channel:')[1].split()[0])
                    except:
                        pass
                elif 'Frequency:' in line:
                    try:
                        freq_str = line.split('Frequency:')[1].split()[0]
                        current_freq = float(freq_str)
                    except:
                        pass
                elif 'Signal level=' in line or 'Quality=' in line:
                    try:
                        if 'Signal level=' in line:
                            sig = line.split('Signal level=')[1].split()[0]
                            current_signal = int(sig.replace('dBm', ''))
                        elif 'Quality=' in line:
                            qual = line.split('Quality=')[1].split()[0]
                            current_signal = int(qual.split('/')[0])
                    except:
                        pass
                elif line.startswith('Cell ') or line == '':
                    # Save previous entry
                    if current_channel > 0 and current_ssid:
                        entry = (current_ssid[:20], current_signal)
                        if current_freq < 3:  # 2.4 GHz
                            if current_channel not in channels_2g:
                                channels_2g[current_channel] = []
                            channels_2g[current_channel].append(entry)
                        else:  # 5 GHz
                            if current_channel not in channels_5g:
                                channels_5g[current_channel] = []
                            channels_5g[current_channel].append(entry)
                    current_ssid = ""
                    current_channel = 0
                    current_signal = 0

            # Build report
            output = "=== 2.4 GHz Channel Usage ===\n"
            for ch in sorted(channels_2g.keys()):
                networks = channels_2g[ch]
                output += f"Ch {ch}: {len(networks)} networks"
                if len(networks) <= 3:
                    names = [n[0] for n in networks]
                    output += f" ({', '.join(names)})"
                output += "\n"

            # Find best 2.4GHz channels (1, 6, 11 are non-overlapping)
            best_2g = []
            for ch in [1, 6, 11]:
                count = len(channels_2g.get(ch, []))
                best_2g.append((ch, count))
            best_2g.sort(key=lambda x: x[1])
            output += f"Best 2.4GHz: Channel {best_2g[0][0]} ({best_2g[0][1]} networks)\n"

            if channels_5g:
                output += "\n=== 5 GHz Channel Usage ===\n"
                for ch in sorted(channels_5g.keys()):
                    networks = channels_5g[ch]
                    output += f"Ch {ch}: {len(networks)} networks\n"

            return ToolResult(content=output)
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
