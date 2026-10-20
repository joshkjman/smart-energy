variable "alert_email" {
    type        = string
    description = "SNS notifications sent to this email address"
    sensitive   = true
}