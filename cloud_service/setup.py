from setuptools import setup, find_packages

setup(
    name="cloud_service",
    version="1.0.0",
    packages=find_packages(include=["cloud_service", "cloud_service.*"]),
    install_requires=[
        "fastapi>=0.68.0",
        "uvicorn>=0.15.0",
        "sqlalchemy>=1.4.0",
        "pydantic>=1.8.0",
        "pydantic-settings>=2.0.0",
        "python-multipart>=0.0.5",
        "aiofiles>=0.7.0",
        "pyyaml>=5.4.0",
        "email-validator>=1.1.0",
        "httpx>=0.24.0",
        "python-dotenv>=1.0.0"
    ],
    python_requires=">=3.8",
) 