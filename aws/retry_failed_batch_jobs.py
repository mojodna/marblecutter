import argparse
import boto3


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


def retry_jobs(queue_arn, since=0):
    client = boto3.client('batch')

    for job_summary in iter_jobs(client, queue_arn, 'FAILED'):
        job_id = job_summary['jobId']

        job_data = client.describe_jobs(jobs=[job_id])['jobs'][0]

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


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'queue',
        help='The AWS Batch queue ARN to look for failed jobs on'
    )
    parser.add_argument(
        '--since',
        type=int,
        help='Only include jobs that have stopped since this UNIX timestamp'
    )

    args = parser.parse_args()

    retry_jobs(args.queue, since=args.since)
