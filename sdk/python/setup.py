from setuptools import setup, find_packages

setup(
    name="alsa-sdk",
    version="1.0.0",
    description="Python SDK for the ALSA Institutional Stock Analysis API",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "httpx>=0.25.0",
        "pydantic>=2.0",
    ],
    extras_require={
        "dev": ["pytest", "pytest-asyncio"],
    },
)
