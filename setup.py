from setuptools import find_packages, setup

version = '0.2.4'

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
        'marblecutter': ['static/images/*', 'templates/*'],
    },
    install_requires=[
        'haversine',
        'mercantile',
        'numpy',
        'Pillow',
        'rasterio[s3]>=1.0a10',
        'scipy',
    ],
    extras_require={
        'color_ramp': 'matplotlib',
        'postgis': 'psycopg2',
        'web': [
            'flask',
            'flask-cors',
        ],
    },
)
