from setuptools import find_packages, setup

version = "0.4.0rc1"

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
        "haversine",
        "mercantile",
        "numexpr",
        "numpy",
        "Pillow",
        "rasterio[s3]>=1.0.9",
        "requests",
        "rio-pansharpen ~= 0.2.0",
        "rio-tiler",
        "rio-toa",
    ],
    extras_require={
        "color_ramp": "matplotlib",
        "postgis": "psycopg2",
        "web": ["flask"],
        # TODO eventually move to environment markers, per https://hynek.me/articles/conditional-python-dependencies/
        ":python_version<'3.0'": ["futures"],
    },
)
