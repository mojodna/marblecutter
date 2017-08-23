from setuptools import find_packages, setup

version = '0.0.0'

setup(
    name='marblecutter',
    version=version,
    description='Raster manipulation',
    url='https://github.com/mojodna/marblecutter',
    author='Seth Fitzsimmons',
    author_email='seth@mojodna.net',
    license='BSD',
    packages=find_packages(),
    zip_safe=False,
    package_data={
        'marblecutter': ['static/*', 'templates/*'],
    },
)
