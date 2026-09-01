from setuptools import setup, find_packages

setup(
    name="zasi",
    version="12.0.0",
    description="Omniscient Sovereign Artificial Superintelligence (ASI) Architecture",
    packages=find_packages(),
    python_requires=">=3.9",
    entry_points={
        "console_scripts": [
            "zasi=src.cli:main",
            "zasi-core=main:main"
        ]
    }
)
