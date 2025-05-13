# components/04-spark/spark-jobs/write_test.py
import os
from pyspark.sql import SparkSession
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, DoubleType

print("Starting Spark Write Test script...")

# --- Configuration ---
# Determine S3 bucket name from environment or use a default
# Ensure your SparkApplication YAML sets this environment variable if needed,
# otherwise, replace the default value here.
S3_BUCKET = os.environ.get("S3_BUCKET_NAME", "spark-data") # Use 'spark-data' if env var not set

# Define Hive schema and table name
HIVE_SCHEMA = "default" # Or choose another existing schema like 'test_trino_s3'
TABLE_NAME = "test_spark_table"
FULL_TABLE_NAME = f"hive.{HIVE_SCHEMA}.{TABLE_NAME}"

# Define the path within the S3 bucket for the table data
# It's good practice to structure paths by schema/table
TABLE_PATH = f"s3a://{S3_BUCKET}/{HIVE_SCHEMA}/{TABLE_NAME}"

# --- Spark Session Initialization ---
try:
    print("Initializing SparkSession with Hive support...")
    spark = SparkSession.builder \
        .appName("SparkWriteTestToMinioHive") \
        .enableHiveSupport() \
        .getOrCreate()
    print("SparkSession initialized successfully.")
    print(f"Using Hive Metastore: {spark.conf.get('spark.hadoop.hive.metastore.uris')}")
    print(f"Default Warehouse Dir: {spark.conf.get('spark.sql.warehouse.dir')}") # Optional check
    print(f"Target S3 Bucket (derived): {S3_BUCKET}")
    print(f"Target S3 Path: {TABLE_PATH}")

except Exception as e:
    print(f"Error initializing SparkSession: {e}")
    raise

# --- Create Sample Data ---
print("Creating sample DataFrame...")
data = [("Alice", 101, 155.5), ("Bob", 102, 180.1), ("Charlie", 103, 175.0)]
schema = StructType([
    StructField("name", StringType(), True),
    StructField("id", IntegerType(), True),
    StructField("height", DoubleType(), True)
])
df = spark.createDataFrame(data, schema)
print("Sample DataFrame created:")
df.show()

# --- Write to Minio and Register in Hive Metastore ---
try:
    print(f"Attempting to write table '{FULL_TABLE_NAME}' to path '{TABLE_PATH}'...")
    # Write the DataFrame to Minio in Parquet format.
    # mode("overwrite"): If the table or path exists, it will be replaced. Use "append" or "errorifexists" as needed.
    # option("path", TABLE_PATH): Explicitly specifies the S3 location for the data files.
    # saveAsTable(FULL_TABLE_NAME): Writes the data and registers the table in the Hive Metastore.
    df.write.format("parquet").mode("overwrite").option("path", TABLE_PATH).saveAsTable(FULL_TABLE_NAME)
    print(f"Successfully wrote and registered table '{FULL_TABLE_NAME}' at '{TABLE_PATH}'.")

except Exception as e:
    print(f"Error writing table '{FULL_TABLE_NAME}': {e}")
    # Optionally, re-raise the exception to make the Spark job fail clearly
    # raise

# --- Stop Spark Session ---
print("Stopping SparkSession...")
spark.stop()
print("Spark Write Test script finished.")
