import argparse
import boto3
import mercantile
import os


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('bucket')
    parser.add_argument('zoom', type=int)
    parser.add_argument('max_zoom', type=int)
    parser.add_argument('--key_prefix')
    args = parser.parse_args()

    client = boto3.client('batch')

    database_url = os.environ.get('DATABASE_URL')
    assert database_url, \
        "Please set a DATABASE_URL environment variable"

    assert args.zoom < args.max_zoom, \
        "Pyramid root zoom must be less than max zoom"

    (w, s, e, n) = (-180.0, -90.0, 180.0, 90.0)

    for tile in mercantile.tiles(w, s, e, n, [args.zoom]):
        command_list = [
            'python', 'examples/render_pyramid.py',
            str(tile.x), str(tile.y), str(tile.z),
            str(args.max_zoom), args.bucket
        ]

        if args.key_prefix:
            command_list.append('--key_prefix')
            command_list.append(args.key_prefix)

        result = client.submit_job(
            jobName='tiler-{}-{}-{}'.format(tile.z, tile.x, tile.y),
            jobDefinition='tiler',
            jobQueue='tiling-20150606',
            containerOverrides={
                'command': command_list,
                'environment': [
                    {'name': 'DATABASE_URL',
                     'value': database_url}
                ]
            }
        )

        print "name: {jobName}, id: {jobId}".format(**result)
