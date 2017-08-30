import argparse
import boto3
import os
from itertools import islice


def grouper(iterable, n):
    """Yield n-length chunks of the iterable"""
    it = iter(iterable)
    while True:
        chunk = tuple(islice(it, n))
        if not chunk:
            return
        yield chunk


def generate_tiles():
    # NOTE this will generate some invalid tile names. GDAL's SRTMHGT will
    # prevent them from actually being created thought
    for ns in ("N", "S"):
        # for lat in range(1):
        for lat in range(90):
            for ew in ("E", "W"):
                # for lon in range(1):
                for lon in range(180):
                    tile = "{}{:02d}{}{:03d}".format(ns, lat, ew, lon)
                    yield tile


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('bucket')
    parser.add_argument('per_job', type=int)
    parser.add_argument('--prefix')
    args = parser.parse_args()

    client = boto3.client('batch')

    database_url = os.environ.get('DATABASE_URL')
    assert database_url, "Please set a DATABASE_URL environment variable"

    for tile_group in grouper(generate_tiles(), args.per_job):
        command_list = [
            'python', 'examples/render_bulk_skadi.py', args.bucket
        ]

        if args.prefix:
            command_list.append('--prefix')
            command_list.append(args.prefix)

        command_list.extend(tile_group)

        result = client.submit_job(
            jobName='skadi-' + tile_group[0],
            jobDefinition='tiler-skadi',
            jobQueue='tiling-skadi-20170829',
            containerOverrides={
                'command': command_list,
                'environment': [
                    {'name': 'DATABASE_URL',
                     'value': database_url},
                ],
                'memory': 6000,
            }
        )

        print "name: {jobName}, id: {jobId}".format(**result)
