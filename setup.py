"""
Setup script for vnpy_tiger
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="vnpy_tiger",
    version="1.0.0",
    author="VeighNa Community",
    author_email="support@vnpy.com",
    description="Tiger Securities gateway for VeighNa trading platform",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/weijiaxing/vnpy_tiger",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Topic :: Office/Business :: Financial :: Investment",
    ],
    python_requires=">=3.9",
    install_requires=[
        "vnpy>=4.0.0",
        "tigeropen>=2.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=6.0",
            "pytest-cov>=2.0",
            "black>=21.0",
            "isort>=5.0",
            "flake8>=3.8",
        ]
    },
    entry_points={
        "vnpy.gateways": [
            "tiger = vnpy_tiger:TigerGateway",
        ]
    },
)