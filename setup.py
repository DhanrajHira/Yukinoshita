from setuptools import setup, find_packages

setup(
    name="yukinoshita",
    version="0.3.0",
    license="MIT",
    author="Dhanraj Hira, Not Marek",
    author_email="hiradhanraj0100@gmail.com",
    description="A simple HLS playlist downloader.",
    long_description=open("README.md", "r").read(),
    long_description_content="text/markdown",
    url="https://github.com/DhanrajHira/Yukinoshita",
    packages=find_packages(),
     classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
    install_requires=[
     "requests==2.22.0",
     "pycryptodome==3.9.7",
     "progress==1.5"
    ]   
)