"""NanoAgent - Lightweight AI Assistant for Raspberry Pi"""

from setuptools import setup, find_packages

setup(
    name="nanoagent",
    version="0.1.0",
    description="Lightweight AI Assistant for Raspberry Pi Zero 2W with Whisplay HAT",
    author="NanoAgent",
    python_requires=">=3.11",
    packages=find_packages(),
    install_requires=[
        "anthropic>=0.40.0",
        "openai>=1.50.0",
        "httpx>=0.27.0",
        "pydantic>=2.0.0",
        "pydantic-settings>=2.0.0",
        "aiofiles>=24.1.0",
        "Pillow>=10.0.0",
        "beautifulsoup4>=4.12.0",
        "duckduckgo-search>=6.0.0",
    ],
    extras_require={
        "pi": [
            "spidev>=3.6",
            "RPi.GPIO>=0.7.1",
        ],
        "dev": [
            "pytest>=8.0.0",
            "pytest-asyncio>=0.23.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "nanoagent=nanoagent.main:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
