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
    parser.add_argument('--only_render')
    parser.add_argument('--vrt_resampling',
                        help='Resampling method used when creating '
                             'overviews from WarpedVRT. See '
                             'https://github.com/mapbox/rasterio/blob/master/rasterio/enums.py#L28.')
    parser.add_argument('--bbox',
                        default='-180.0,-90.0,180.0,90.0',
                        help='Bounding box of tiles to submit jobs. '
                             'format: left,bottom,right,top')
    parser.add_argument('--overwrite', dest='overwrite',
                        action='store_true', default=False)
    args = parser.parse_args()

    client = boto3.client('batch')

    database_url = os.environ.get('DATABASE_URL')
    assert database_url, \
        "Please set a DATABASE_URL environment variable"

    assert args.zoom < args.max_zoom, \
        "Pyramid root zoom must be less than max zoom"

    (w, s, e, n) = map(float, args.bbox.split(','))

    for tile in mercantile.tiles(w, s, e, n, [args.zoom]):
        command_list = [
            'python', 'examples/render_pyramid.py',
            str(tile.x), str(tile.y), str(tile.z),
            str(args.max_zoom), args.bucket
        ]

        if args.key_prefix:
            command_list.append('--key_prefix')
            command_list.append(args.key_prefix)

        container_overrides = {
            'command': command_list,
            'environment': [
                {'name': 'DATABASE_URL',
                 'value': database_url},
            ]
        }

        if args.overwrite:
            container_overrides['environment'].append(
                {'name': 'OVERWRITE_EXISTING_OBJECTS', 'value': 'true'}
            )

        if args.vrt_resampling:
            container_overrides['environment'].append(
                {'name': 'RESAMPLING_METHOD', 'value': args.vrt_resampling}
            )

        if args.only_render:
            container_overrides['environment'].append(
                {'name': 'ONLY_RENDER', 'value': args.only_render}
            )

        result = client.submit_job(
            jobName='tiler-{}-{}-{}'.format(tile.z, tile.x, tile.y),
            jobDefinition='tiler',
            jobQueue='tiling-20150606',
            containerOverrides=container_overrides,
        )

        print "name: {jobName}, id: {jobId}".format(**result)
