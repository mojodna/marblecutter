from setuptools import find_packages, setup

version = "0.3.1"

setup(
    name="marblecutter",
    version=version,
    description="Raster manipulation",
    url="https://github.com/mojodna/marblecutter",
    author="Seth Fitzsimmons",
    author_email="seth@mojodna.net",
    license="BSD",
    packages=find_packages(),
    zip_safe=False,
    package_data={"marblecutter": ["static/images/*", "templates/*"]},
    install_requires=[
        "future",
        "futures",
        "haversine",
        "mercantile",
        "numpy",
        "Pillow",
        "rasterio[s3]>=1.0.6",
        "requests",
        "rio-pansharpen ~= 0.2.0",
        # TODO upgrade me
        "rio-tiler ~= 0.0.3",
        "rio-toa",
    ],
    # dependency_links=[
    #     'https://github.com/mapbox/rasterio/archive/master.tar.gz#egg=rasterio[s3]',
    # ],
    extras_require={
        "color_ramp": "matplotlib",
        "postgis": "psycopg2",
        "web": ["flask", "flask-cors"],
    },
)
