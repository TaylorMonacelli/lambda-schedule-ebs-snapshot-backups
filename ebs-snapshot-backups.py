import boto3
import collections
import datetime

ec = boto3.client('ec2')


def lambda_handler(event, context):

    client = boto3.client('ec2')
    regions = [region['RegionName']
               for region in client.describe_regions()['Regions']]

    for r in regions:
        print("region: %s" % r)

        ec = boto3.client('ec2', region_name=r)

        reservations = ec.describe_instances(
            Filters=[
                {'Name': 'tag-key', 'Values': ['backup', 'Backup']},
            ]
        ).get(
            'Reservations', []
        )

        instances = [
            i for r in reservations
            for i in r['Instances']
        ]

        print("Found %d instances that need backing up" % len(instances))

        to_tag = collections.defaultdict(list)

        for instance in instances:
            try:
                retention_days = [
                    int(t.get('Value')) for t in instance['Tags']
                    if t['Key'] == 'Retention'][0]
            except IndexError:
                retention_days = 7

            for dev in instance['BlockDeviceMappings']:
                if dev.get('Ebs', None) is None:
                    continue
                vol_id = dev['Ebs']['VolumeId']
                print("Found EBS volume %s on instance %s" % (
                    vol_id, instance['InstanceId']))

                snap = ec.create_snapshot(
                    VolumeId=vol_id,
                )

                to_tag[retention_days].append(snap['SnapshotId'])

                print("Retaining snapshot %s of volume %s from instance %s for %d days" % (
                    snap['SnapshotId'],
                    vol_id,
                    instance['InstanceId'],
                    retention_days,
                ))

                for retention_days in to_tag.keys():
                    delete_date = datetime.date.today() + datetime.timedelta(days=retention_days)
                    delete_fmt = delete_date.strftime('%Y-%m-%d')
                    print("Will delete %d snapshots on %s" %
                          (len(to_tag[retention_days]), delete_fmt))
                    ec.create_tags(
                        Resources=to_tag[retention_days],
                        Tags=[
                            {'Key': 'DeleteOn', 'Value': delete_fmt},
                        ]
                    )
