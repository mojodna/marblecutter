#!/usr/bin/env python
# coding=utf-8

from __future__ import print_function

import sys

from get_zoom import get_resolution


if __name__ == "__main__":
    if len(sys.argv) == 1:
        print("usage: {} <input>".format(os.path.basename(sys.argv[0])), file=sys.stderr)
        exit(1)

    input = sys.argv[1]
    try:
        print(get_resolution(input))
    except IOError:
        print("Unable to open '{}'.".format(input), file=sys.stderr)
        exit(1)
