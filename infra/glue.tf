resource "aws_glue_catalog_table" "demand" {
  name          = "demand"
  database_name = aws_glue_catalog_database.bronze.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    "classification"                           = "json"
    "projection.enabled"                       = "true"
    "projection.settlement_date.type"          = "date"
    "projection.settlement_date.format"        = "yyyy-MM-dd"
    "projection.settlement_date.range"         = "2024-07-01,NOW"
    "projection.settlement_date.interval"      = "1"
    "projection.settlement_date.interval.unit" = "DAYS"
    "storage.location.template"                = "s3://smart-energy-lake/bronze/demand/settlement_date=$${settlement_date}"
  }

  partition_keys {
    name = "settlement_date"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://smart-energy-lake/bronze/demand/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      serialization_library = "org.openx.data.jsonserde.JsonSerDe"
    }

    columns {
      name = "data"
      type = "array<struct<publishtime:string,starttime:string,settlementdate:string,settlementperiod:int,initialdemandoutturn:int,initialtransmissionsystemdemandoutturn:int>>"
    }
  }
}


resource "aws_glue_catalog_table" "weather_forecast" {
  name          = "weather_forecast"
  database_name = aws_glue_catalog_database.bronze.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    "classification"                      = "json"
    "projection.enabled"                  = "true"
    "projection.issue_date.type"          = "date"
    "projection.issue_date.format"        = "yyyy-MM-dd"
    "projection.issue_date.range"         = "2024-06-24,NOW"
    "projection.issue_date.interval"      = "1"
    "projection.issue_date.interval.unit" = "DAYS"
    "storage.location.template"           = "s3://smart-energy-lake/bronze/weather_forecast/issue_date=$${issue_date}"
  }

  partition_keys {
    name = "issue_date"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://smart-energy-lake/bronze/weather_forecast/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      serialization_library = "org.openx.data.jsonserde.JsonSerDe"
    }

    columns {
      name = "data"
      type = "array<struct<target_ts:string,variable:string,value:double,n:int,issue_ts:string>>"
    }
  }
}


resource "aws_glue_catalog_table" "bank_holidays" {
  name          = "bank_holidays"
  database_name = aws_glue_catalog_database.bronze.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    "classification" = "json"
  }

  storage_descriptor {
    location      = "s3://smart-energy-lake/bronze/bank_holidays/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      serialization_library = "org.openx.data.jsonserde.JsonSerDe"
      parameters = {
        "mapping.england_and_wales" = "england-and-wales"
        "mapping.northern_ireland"  = "northern-ireland"
        "ignore.malformed.json"     = "false"
      }
    }

    columns {
      name = "england_and_wales"
      type = "struct<division:string,events:array<struct<title:string,date:string,notes:string,bunting:boolean>>>"
    }
    columns {
      name = "northern_ireland"
      type = "struct<division:string,events:array<struct<title:string,date:string,notes:string,bunting:boolean>>>"
    }
    columns {
      name = "scotland"
      type = "struct<division:string,events:array<struct<title:string,date:string,notes:string,bunting:boolean>>>"
    }
  }
}


resource "aws_glue_catalog_database" "bronze" {
  name = "bronze"
}
