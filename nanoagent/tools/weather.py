"""Weather tool using Open-Meteo API"""

import httpx
from .base import Tool, ToolResult


class WeatherTool(Tool):
    """Get current weather for a location"""

    @property
    def name(self) -> str:
        return "weather"

    @property
    def description(self) -> str:
        return "Get current weather conditions for a location (temperature, wind, conditions)"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City name or location (e.g., 'London', 'New York', 'Tokyo')",
                },
            },
            "required": ["location"],
        }

    async def execute(self, location: str, **kwargs) -> ToolResult:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                # Step 1: Geocode the location
                geo_url = "https://geocoding-api.open-meteo.com/v1/search"
                geo_resp = await client.get(geo_url, params={
                    "name": location,
                    "count": 1,
                    "language": "en",
                    "format": "json",
                })
                geo_data = geo_resp.json()

                if "results" not in geo_data or not geo_data["results"]:
                    return ToolResult.error(f"Location '{location}' not found")

                place = geo_data["results"][0]
                lat = place["latitude"]
                lon = place["longitude"]
                place_name = place.get("name", location)
                country = place.get("country", "")

                # Step 2: Get weather
                weather_url = "https://api.open-meteo.com/v1/forecast"
                weather_resp = await client.get(weather_url, params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,wind_direction_10m",
                    "temperature_unit": "celsius",
                    "wind_speed_unit": "kmh",
                })
                weather_data = weather_resp.json()

                if "current" not in weather_data:
                    return ToolResult.error("Failed to get weather data")

                current = weather_data["current"]

                # Decode weather code
                condition = self._decode_weather_code(current.get("weather_code", 0))

                # Format output
                temp = current.get("temperature_2m", "N/A")
                feels_like = current.get("apparent_temperature", "N/A")
                humidity = current.get("relative_humidity_2m", "N/A")
                wind_speed = current.get("wind_speed_10m", "N/A")
                wind_dir = self._wind_direction(current.get("wind_direction_10m", 0))

                output = f"""Weather for {place_name}, {country}:
Condition: {condition}
Temperature: {temp}°C (feels like {feels_like}°C)
Humidity: {humidity}%
Wind: {wind_speed} km/h {wind_dir}"""

                return ToolResult.success(output)

        except httpx.TimeoutException:
            return ToolResult.error("Weather request timed out")
        except Exception as e:
            return ToolResult.error(f"Weather error: {e}")

    def _decode_weather_code(self, code: int) -> str:
        """Convert WMO weather code to description"""
        codes = {
            0: "Clear sky",
            1: "Mainly clear",
            2: "Partly cloudy",
            3: "Overcast",
            45: "Foggy",
            48: "Depositing rime fog",
            51: "Light drizzle",
            53: "Moderate drizzle",
            55: "Dense drizzle",
            61: "Slight rain",
            63: "Moderate rain",
            65: "Heavy rain",
            66: "Light freezing rain",
            67: "Heavy freezing rain",
            71: "Slight snow",
            73: "Moderate snow",
            75: "Heavy snow",
            77: "Snow grains",
            80: "Slight rain showers",
            81: "Moderate rain showers",
            82: "Violent rain showers",
            85: "Slight snow showers",
            86: "Heavy snow showers",
            95: "Thunderstorm",
            96: "Thunderstorm with slight hail",
            99: "Thunderstorm with heavy hail",
        }
        return codes.get(code, f"Unknown ({code})")

    def _wind_direction(self, degrees: float) -> str:
        """Convert degrees to compass direction"""
        directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        idx = round(degrees / 45) % 8
        return directions[idx]
