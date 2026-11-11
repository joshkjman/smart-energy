# Teardown

This doc is for knowing how to tear down the infrastructure of this project not on a constant basis, as costs aren't high it can run for long periods of time.

## Should this be a full teardown?

Some things can be left, but the one that matters is S3 as it is the highest cost right now. Nearly all of that is requests, not storage ($1.89 vs $0.03 in October), so disabling the schedules stops most of the bill without deleting anything. A full destroy only saves the $0.03 of storage.

## Order of operations

- Terraform destroy
- Delete smart-energy-tfstate bucket last manually
- For buckets with versioning, delete all versions first then delete bucket

### 1. Stop the schedule first

disable-rule first so that it doesn't create new partitions in bucket in automated ingestion

```bash
for r in demand_ingest_event weather_ingest_event weather_actual_event sfn_state_machine_event; do
  aws events disable-rule --name "$r" --region eu-west-2
done
aws stepfunctions list-executions --state-machine-arn <arn> \
  --status-filter RUNNING --region eu-west-2
```

### 2. `terraform destroy`

Goes cleanly (all declared in `infra/`): 4 Lambdas + 2 layers, 5 CloudWatch log
groups, Step Function, CodeBuild project, 7 IAM roles + inline policies, 4
EventBridge rules + targets, SNS topic + subscription, Athena workgroup
(`force_destroy = true`), 3 Glue databases + 5 bronze tables.

Fails on `aws_s3_bucket.smart_energy_bucket` — `BucketNotEmpty`.

That failure is good because it means one wrong accidental command won't delete all
forecast history data, so acts as slight protection.
DeleteDatabase deletes everything contained in that database, including those silver/
gold CTAS.

### 3. Empty and delete `smart-energy-lake`

Export the data in this bucket so you don't have to rebuild or lose historical
forecast data.

### 4. Delete `smart-energy-tfstate` — last, by hand

Not in any Terraform state; it holds it (`infra/backend.tf`). Also holds the
`use_lockfile = true` lock object and every historical state version.

## Deleting a versioned bucket

`aws s3 rb --force` runs `rm --recursive`, which writes delete markers over the
current versions. The bucket then reads as empty in the console's default view
while still holding every noncurrent version plus the markers, and `rb` fails.

Console: the bucket's **Empty** button handles versions correctly.

CLI: versions and delete markers are separate lists, so two passes, each looping
until empty (`delete-objects` caps at 1000 keys per call):

```bash
B=smart-energy-lake   # repeat for smart-energy-tfstate

aws s3api delete-objects --bucket "$B" --delete "$(aws s3api list-object-versions \
  --bucket "$B" --max-items 1000 \
  --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}}' --output json)"

aws s3api delete-objects --bucket "$B" --delete "$(aws s3api list-object-versions \
  --bucket "$B" --max-items 1000 \
  --query '{Objects: DeleteMarkers[].{Key:Key,VersionId:VersionId}}' --output json)"

aws s3 rb "s3://$B"
```

Gotcha: an already-empty list yields `{"Objects": null}`, which errors rather
than no-ops. That's your stop condition.

## Partial teardown — stop the bill, keep the history

Stop the S3 request traffic those queries generate from running as they are the 
non-free tier items and means you don't need to rebuild history like you would 
have to for data in S3.

S3, October:   requests  $1.89   ← schedule-driven, stops when rules are disabled
               storage   $0.03   ← the only thing deleting data saves

## What survives, deliberately

- Billing alarm — console-only, not in `infra/`.
- IAM user and its MFA device.