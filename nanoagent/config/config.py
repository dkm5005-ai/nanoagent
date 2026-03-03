"""Configuration management for NanoAgent"""

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ProviderConfig(BaseModel):
    """Configuration for an LLM provider"""
    api_key: str = ""
    api_base: str | None = None


class ModelConfig(BaseModel):
    """Configuration for a model alias"""
    name: str  # User-facing alias (e.g., "claude", "gpt4")
    provider: str  # Provider type: "anthropic", "openai", "openrouter"
    model: str  # Actual model ID (e.g., "claude-sonnet-4-20250514")
    api_key: str | None = None  # Override provider API key
    api_base: str | None = None  # Override provider API base
    max_tokens: int = 4096
    temperature: float = 0.7


class VoiceConfig(BaseModel):
    """Configuration for voice input/output"""
    enabled: bool = True

    # Speech-to-text
    stt_provider: str = "openai"  # "openai" or "groq"
    stt_model: str = "whisper-1"

    # Text-to-speech
    tts_enabled: bool = True
    tts_provider: str = "openai"
    tts_model: str = "tts-1"
    tts_voice: str = "alloy"  # alloy, echo, fable, onyx, nova, shimmer

    # Audio settings
    sample_rate: int = 48000  # 48kHz for Radxa/WM8960
    channels: int = 2


class ToolsConfig(BaseModel):
    """Configuration for agent tools"""
    enabled: list[str] = Field(default_factory=lambda: [
        "read_file", "write_file", "edit_file", "list_dir",
        "exec", "web_search", "web_fetch"
    ])

    # Shell tool settings
    shell_deny_patterns: list[str] = Field(default_factory=lambda: [
        "rm -rf /", "rm -rf /*", "mkfs", "dd if=",
        ":(){:|:&};:", "chmod -R 777 /", "shutdown", "reboot"
    ])

    # Workspace restriction
    restrict_to_workspace: bool = True


class HardwareConfig(BaseModel):
    """Configuration for Whisplay HAT hardware"""
    enabled: bool = True

    # Driver path (auto-detected if not set)
    driver_path: str | None = None

    # Display settings
    lcd_width: int = 240
    lcd_height: int = 280
    backlight_brightness: int = 60  # 0-100

    # LED settings
    led_idle_color: tuple[int, int, int] = (0, 0, 255)  # Blue
    led_listening_color: tuple[int, int, int] = (255, 0, 0)  # Red
    led_thinking_color: tuple[int, int, int] = (255, 255, 0)  # Yellow
    led_speaking_color: tuple[int, int, int] = (0, 255, 0)  # Green

    # Audio device
    audio_card: str = "wm8960soundcard"


class AgentConfig(BaseModel):
    """Configuration for the agent behavior"""
    max_tool_iterations: int = 20
    max_history_messages: int = 50
    system_prompt_cache: bool = True


class Config(BaseModel):
    """Main configuration for NanoAgent"""
    # Paths
    workspace: str = "~/.nanoagent/workspace"
    config_path: str | None = None

    # Providers (API keys)
    providers: dict[str, ProviderConfig] = Field(default_factory=lambda: {
        "anthropic": ProviderConfig(),
        "openai": ProviderConfig(),
        "openrouter": ProviderConfig(api_base="https://openrouter.ai/api/v1"),
    })

    # Model definitions
    models: list[ModelConfig] = Field(default_factory=lambda: [
        ModelConfig(
            name="gpt4-mini",
            provider="openai",
            model="gpt-4o-mini",
        ),
        ModelConfig(
            name="gpt4",
            provider="openai",
            model="gpt-4o",
        ),
        ModelConfig(
            name="claude",
            provider="anthropic",
            model="claude-sonnet-4-20250514",
        ),
    ])

    # Default model to use (gpt4-mini is fastest)
    default_model: str = "gpt4-mini"

    # Subsystem configs
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    hardware: HardwareConfig = Field(default_factory=HardwareConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)

    def get_model_config(self, name: str | None = None) -> ModelConfig:
        """Get model configuration by name"""
        name = name or self.default_model
        for model in self.models:
            if model.name == name:
                return model
        raise ValueError(f"Model '{name}' not found in configuration")

    def get_provider_config(self, provider: str) -> ProviderConfig:
        """Get provider configuration"""
        if provider not in self.providers:
            raise ValueError(f"Provider '{provider}' not found in configuration")
        return self.providers[provider]

    def get_api_key(self, model_name: str | None = None) -> str:
        """Get API key for a model (checks model override, then provider)"""
        model = self.get_model_config(model_name)
        if model.api_key:
            return model.api_key
        provider = self.get_provider_config(model.provider)
        return provider.api_key

    def get_workspace_path(self) -> Path:
        """Get expanded workspace path"""
        return Path(self.workspace).expanduser()

    def ensure_workspace(self) -> None:
        """Create workspace directories if they don't exist"""
        workspace = self.get_workspace_path()
        (workspace / "sessions").mkdir(parents=True, exist_ok=True)
        (workspace / "memory").mkdir(parents=True, exist_ok=True)


def load_config(config_path: str | None = None) -> Config:
    """Load configuration from file or environment"""
    # Default config paths
    default_paths = [
        Path.cwd() / "config.json",
        Path.home() / ".nanoagent" / "config.json",
        Path("/etc/nanoagent/config.json"),
    ]

    # Use provided path or search defaults
    if config_path:
        paths_to_try = [Path(config_path)]
    else:
        paths_to_try = default_paths

    config_data: dict[str, Any] = {}

    # Try to load from file
    for path in paths_to_try:
        if path.exists():
            with open(path) as f:
                config_data = json.load(f)
            config_data["config_path"] = str(path)
            break

    # Override with environment variables
    env_mappings = {
        "ANTHROPIC_API_KEY": ("providers", "anthropic", "api_key"),
        "OPENAI_API_KEY": ("providers", "openai", "api_key"),
        "OPENROUTER_API_KEY": ("providers", "openrouter", "api_key"),
        "NANOAGENT_WORKSPACE": ("workspace",),
        "NANOAGENT_DEFAULT_MODEL": ("default_model",),
    }

    for env_var, path in env_mappings.items():
        value = os.environ.get(env_var)
        if value:
            # Navigate to the right place in config_data
            current = config_data
            for key in path[:-1]:
                if key not in current:
                    current[key] = {}
                current = current[key]
            current[path[-1]] = value

    return Config(**config_data)


def save_config(config: Config, path: str | None = None) -> None:
    """Save configuration to file"""
    save_path = Path(path or config.config_path or "~/.nanoagent/config.json").expanduser()
    save_path.parent.mkdir(parents=True, exist_ok=True)

    with open(save_path, "w") as f:
        json.dump(config.model_dump(), f, indent=2)
