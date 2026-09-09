from pyathena import connect
from pyathena.pandas.cursor import PandasCursor


def get_athena_connection():
    return connect(
        s3_staging_dir="s3://smart-energy-lake/athena-results/",
        region_name="eu-west-2",
        schema_name="gold",
        work_group="foresight_queries",
        cursor_class=PandasCursor,
    )