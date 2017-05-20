# noqa
# coding=utf-8
from __future__ import print_function

from marblecutter import skadi

if __name__ == "__main__":
    tile = "N38W123"
    (content_type, data) = skadi.render_tile(tile)

    print("Content-type: ", content_type)

    with open("tmp/{}.hgt.gz".format(tile), "w") as f:
        f.write(data)
