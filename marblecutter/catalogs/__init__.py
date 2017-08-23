from rasterio.crs import CRS

WGS84_CRS = CRS.from_epsg(4326)


class Catalog(object):
    @property
    def bounds(self):
        return [-180, -85.05113, 180, 85.05113]

    @property
    def center(self):
        return [0, 0, 2]

    @property
    def id(self):
        return None

    @property
    def maxzoom(self):
        return 22

    @property
    def metadata_url(self):
        return None

    @property
    def minzoom(self):
        return 0

    @property
    def name(self):
        return "Untitled"

    @property
    def provider(self):
        return None

    @property
    def provider_url(self):
        return None

    def get_sources(self, (bounds, bounds_crs), resolution):
        raise NotImplemented
