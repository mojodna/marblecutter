import argparse
import boto3
import mercantile


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('from_bucket')
    parser.add_argument('to_bucket')
    parser.add_argument('zoom', type=int)
    parser.add_argument('max_zoom', type=int)
    parser.add_argument('--from_prefix')
    parser.add_argument('--to_prefix')
    parser.add_argument('--remove_hash', dest='remove_hash', action='store_true', default=False)
    parser.add_argument('--copy_only')
    parser.add_argument('--cutoff_date')
    parser.add_argument('--verbose', action='store_true', default=False)
    parser.add_argument('--bbox',
                        default='-180.0,-90.0,180.0,90.0',
                        help='Bounding box of tiles to submit jobs. '
                             'format: left,bottom,right,top')
    args = parser.parse_args()

    client = boto3.client('batch')

    assert args.zoom < args.max_zoom, \
        "Pyramid root zoom must be less than max zoom"

    (w, s, e, n) = map(float, args.bbox.split(','))

    for tile in mercantile.tiles(w, s, e, n, [args.zoom]):
        command_list = [
            'python', 'examples/aws_s3_tile_cp.py',
            str(tile.x), str(tile.y), str(tile.z),
            str(args.max_zoom), args.from_bucket, args.to_bucket,
        ]

        if args.from_prefix:
            command_list.append('--from_prefix')
            command_list.append(args.from_prefix)

        if args.to_prefix:
            command_list.append('--to_prefix')
            command_list.append(args.to_prefix)

        if args.remove_hash:
            command_list.append('--remove_hash')

        env_vars = []
        if args.copy_only:
            env_vars.append({
                'name': 'ONLY_COPY',
                'value': args.copy_only,
            })

        if args.cutoff_date:
            env_vars.append({
                'name': 'CUTOFF_DATE',
                'value': args.cutoff_date,
            })

        if args.verbose:
            env_vars.append({
                'name': 'VERBOSE',
                'value': 'true',
            })

        container_overrides = {
            'command': command_list,
        }

        if env_vars:
            container_overrides['environment'] = env_vars

        result = client.submit_job(
            jobName='copy-{}-{}-{}'.format(tile.z, tile.x, tile.y),
            jobDefinition='tilecopy',
            jobQueue='copying-20171106',
            containerOverrides=container_overrides,
        )

        print "name: {jobName}, id: {jobId}".format(**result)
