import os

from setuptools import setup, find_packages

from bup.__version__ import __version__, __title__, __author__, __author_email__, __url__, __download_url__, __description__

readme_file_path = os.path.join("readme.md")

with open(readme_file_path, encoding="utf-8") as f:
    long_description = "\n" + f.read()

setup(
    name=__title__,
    description=__description__,
    long_description=long_description,
    long_description_content_type="text/markdown",
    version=__version__,
    author=__author__,
    author_email=__author_email__,
    license="GPL v3",
    url=__url__,
    download_url=__download_url__,
    keywords=["aws", "dynamodb", "s3", "github", "backup"],
    packages=find_packages(),

    # will be installed in the application parent directory
    data_files=[('', ["LICENSE", "LICENSE.txt", "gpl-3.0.md", readme_file_path])],

    package_data={__title__: [f"{__title__}.png"]},
    install_requires=["ismain", "balsa", "boto3", "typeguard", "hashy", "dictim", "awsimple", "pressenter2exit", "awscli", "GitPython", "github3.py", "sqlitedict", "tobool", "attrs",
                      "appdirs", "pref", "pyqt5"],
    classifiers=[],
)
