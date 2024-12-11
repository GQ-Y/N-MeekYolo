from setuptools import setup, find_packages

setup(
    name="cloud_service",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "fastapi>=0.68.0",
        "uvicorn>=0.15.0",
        "sqlalchemy>=1.4.0",
        "pydantic>=1.8.0",
        "python-multipart>=0.0.5",
        "aiofiles>=0.7.0",
        "pyyaml>=5.4.0",
        "email-validator>=1.1.0",
        "aiohttp>=3.8.0",
        "httpx>=0.24.0",
        "python-dotenv>=1.0.0"
    ],
    author="Your Name",
    author_email="your.email@example.com",
    description="Cloud Model Market Service",
    keywords="cloud,model,market,ai",
    python_requires=">=3.8",
) 