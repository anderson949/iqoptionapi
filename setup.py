"""The python wrapper for IQ Option API package setup."""
from setuptools import (setup, find_packages)
from iqoptionapi.version_control import api_version

setup(
    name="iqoptionapi",
    version=api_version,
    packages=find_packages(),
    install_requires=["pylint", "requests", "websocket-client==1.8.0"],
    include_package_data=True,
    description="Best IQ Option API for python",
    long_description="Best IQ Option API for python",
    url="https://github.com/anderson949/iqoptionapi",
    author="@stealthlord_anonymous",
    zip_safe=False
)
