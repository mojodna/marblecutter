# AWS Automation

These are CloudFormation + AWS Batch configurations (Batch is not yet supported
by CloudFormation).

## TODO

* VPC subnets and security groups must be modified in
  `compute-environment.json.hbs`.
* The `ecsInstanceProfile` must be modified in
  `compute-environment.json.hbs`.
* The Docker image to use must be modified in
  `transcode-job-definition.json.hbs`.
