import argparse
import boto3
import time
from itertools import islice


def iter_jobs(client, queue_arn, status):
    next_token = ''
    while True:
        result = client.list_jobs(
            jobQueue=queue_arn, jobStatus=status, nextToken=next_token)

        job_summary_list = result.get('jobSummaryList')
        for job in job_summary_list:
            yield job

        next_token = result.get('nextToken')

        if next_token is None:
            break


def grouper(n, iterable):
    iterable = iter(iterable)
    return iter(lambda: list(islice(iterable, n)), [])


def retry_jobs(queue_arn, wait=0, since=0):
    client = boto3.client('batch')
    oldest_timestamp = None
    job_count = 0

    for summary_group in grouper(50, iter_jobs(client, queue_arn, 'FAILED')):
        job_ids = [summary['jobId'] for summary in filter(None, summary_group)]

        job_datas = client.describe_jobs(jobs=job_ids)['jobs']

        for job_data in job_datas:
            stopped_at = job_data['stoppedAt']
            if oldest_timestamp is None or stopped_at > oldest_timestamp:
                oldest_timestamp = stopped_at
            job_count += 1

            if job_data['stoppedAt'] <= since:
                print "Skipping job {} ({}) that stopped at {} because it's too old".format(
                    job_data['jobName'],
                    job_data['jobId'],
                    job_data['stoppedAt'],
                )
                continue

            cloned_job = {
                'jobName': job_data['jobName'],
                'jobQueue': job_data['jobQueue'],
                'jobDefinition': job_data['jobDefinition'],
                'containerOverrides': {
                    'vcpus': job_data['container']['vcpus'],
                    'memory': job_data['container']['memory'],
                    'command': job_data['container']['command'],
                    'environment': job_data['container']['environment'],
                },
                'retryStrategy': job_data['retryStrategy'],
            }

            submitted_job = client.submit_job(**cloned_job)

            print "Re-submitted job {} ({}) that stopped at {} and got jobId {}".format(
                job_data['jobName'],
                job_data['jobId'],
                job_data['stoppedAt'],
                submitted_job['jobId']
            )

            time.sleep(wait / 1000.0)

    print "Saw {} jobs in FAILED queue. Oldest job stopped at {}".format(
        job_count,
        oldest_timestamp
    )


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'queue',
        help='The AWS Batch queue ARN to look for failed jobs on'
    )
    parser.add_argument(
        '--wait',
        type=int,
        default=0,
        help='Wait this many milliseconds between each job submission'
    )
    parser.add_argument(
        '--since',
        type=int,
        help='Only include jobs that have stopped since this UNIX timestamp'
    )

    args = parser.parse_args()

    retry_jobs(args.queue, wait=args.wait, since=args.since)
