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
      Next: "DbtBuild"
    },
    DbtBuild:   {
      Type: "Task",
      Resource: "arn:aws:states:::codebuild:startBuild.sync"
      Parameters: {
        ProjectName: aws_codebuild_project.dbt.name
      },
      Next: "Inference"
    },
    "Inference":  { 
      Type: "Task"
      Resource: "arn:aws:states:::lambda:invoke"
      Parameters: { 
        FunctionName: aws_lambda_function.inference_lambda_function.arn
        Payload: {} 
      }
      End: true
    }
  }
})
}