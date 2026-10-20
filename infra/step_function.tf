resource "aws_sfn_state_machine" "nightly" {
  name     = "smart-energy-nightly"
  role_arn = aws_iam_role.sfn_state_machine_role.arn

  definition = jsonencode ({
  Comment: "Nightly: ingest -> freshness -> dbt -> inference"
  StartAt: "DemandIngest",
  States: {
    "DemandIngest": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke"
      "Parameters": { 
        FunctionName: aws_lambda_function.demand_ingest_lambda_function.arn
        "Payload": {} 
      }
      "Retry": [{
        "ErrorEquals": [
          "Lambda.ServiceException",
          "Lambda.AWSLambdaException",
          "Lambda.SdkClientException",
          "Lambda.TooManyRequestsException",
          "States.Timeout"
        ],
        "IntervalSeconds": 30, "MaxAttempts": 3, "BackoffRate": 2.0
      }],
      "Catch": [{ "ErrorEquals": ["States.ALL"], "Next": "NotifyFailure", "ResultPath": "$.error.DemandIngest" }],
      Next: "SourceFreshness"
    },
    SourceFreshness: {
      Type: "Task",
      Resource: "arn:aws:states:::codebuild:startBuild.sync"
      Parameters: {
        ProjectName: aws_codebuild_project.dbt.name
        BuildspecOverride = <<-SPEC
            version: 0.2
            phases:
              install:
                runtime-versions:
                  python: 3.12
                commands:
                  - pip install -r requirements-dbt.txt
              build:
                commands:
                  - cd dbt
                  - dbt deps
                  - dbt source freshness --profiles-dir .
          SPEC
      }
      "Catch": [{ "ErrorEquals": ["States.ALL"], "Next": "NotifyFailure", "ResultPath": "$.error.SourceFreshness" }],
      Next: "DbtBuild"
    },
    DbtBuild:   {
      Type: "Task",
      Resource: "arn:aws:states:::codebuild:startBuild.sync"
      Parameters: {
        ProjectName: aws_codebuild_project.dbt.name
      }
      "Retry": [{
        "ErrorEquals": ["States.TaskFailed"],
        "IntervalSeconds": 30, "MaxAttempts": 1, "BackoffRate": 2.0
      }],
      "Catch": [{ "ErrorEquals": ["States.ALL"], "Next": "NotifyFailure", "ResultPath": "$.error.DbtBuild" }],
      Next: "Inference"
    },
    "Inference":  { 
      Type: "Task"
      Resource: "arn:aws:states:::lambda:invoke"
      Parameters: { 
        FunctionName: aws_lambda_function.inference_lambda_function.arn
        Payload: {} 
      }
      "Retry": [{
        "ErrorEquals": [
          "Lambda.ServiceException",
          "Lambda.AWSLambdaException",
          "Lambda.SdkClientException",
          "Lambda.TooManyRequestsException",
          "States.Timeout"
        ],
        "IntervalSeconds": 30, "MaxAttempts": 3, "BackoffRate": 2.0
      }],
      "Catch": [{ "ErrorEquals": ["States.ALL"], "Next": "NotifyFailure", "ResultPath": "$.error.Inference" }],
      End: true
    },
    "NotifyFailure": {
      "Type": "Task",
      "Resource": "arn:aws:states:::sns:publish",
      "Parameters": {
        "TopicArn": aws_sns_topic.alerts.arn,
        "Subject": "Foresight nightly chain failed",
        "Message.$": "States.JsonToString($.error)"
      },
      "Next": "ChainFailed"
    },
    "ChainFailed": { "Type": "Fail", "Error": "NightlyChainFailed" }
  }
})
}