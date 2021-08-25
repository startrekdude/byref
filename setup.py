import setuptools

from shutil import rmtree

with open("README.md") as f:
	long_description = f.read()

long_description = ""

setuptools.setup(
	name="byref",
	version="0.9",
	author="Sam Haskins",
	description="Pass parameters by reference—in Python!",
	long_description=long_description,
	long_description_content_type="text/markdown",
	url="https://github.com/startrekdude/byref",
	license="ISC",
	packages=setuptools.find_packages(),
	classifiers=[
		"Programming Language :: Python :: 3",
		"License :: OSI Approved :: ISC License (ISCL)",
		"Operating System :: OS Independent",
	],
	python_requires=">=3.9",
)

rmtree("build")
rmtree("byref.egg-info")