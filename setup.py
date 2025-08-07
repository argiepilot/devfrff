"""Setup script for Germany VFR Approach Charts for ForeFlight BYOP."""

from setuptools import find_packages, setup

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="devfrff",
    version="0.1.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="Germany VFR Approach Charts for ForeFlight BYOP",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/devfrff",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Aviation",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.10",
    install_requires=[
        "requests>=2.25.0",
        "beautifulsoup4>=4.9.0",
        "lxml>=4.6.0",
        "pillow>=8.0.0",
        "reportlab>=3.6.0",
        "tqdm>=4.60.0",
        "rich>=10.0.0",
        "typer>=0.4.0",
        "img2pdf>=0.4.0",
    ],
    extras_require={
        "dev": [
            "pytest>=6.0.0",
            "mypy>=0.900",
            "black>=21.0.0",
            "isort>=5.0.0",
            "flake8>=3.8.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "devfrff=src.main:app",
        ],
    },
) 