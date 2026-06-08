from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="benergy-agent",
    version="0.1.0",
    author="Benergy",
    author_email="hello@benergy.io",
    description="GPU monitoring agent for Benergy - tracks GPU utilization and costs",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Benergy-io/Benergy",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Topic :: System :: Monitoring",
    ],
    python_requires=">=3.8",
    install_requires=[
        "requests>=2.28.0",
    ],
    entry_points={
        "console_scripts": [
            "benergy-agent=benergy_agent:main",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
