import findspark
findspark.init()
import os
from pyspark.sql import SparkSession
from pyspark.sql import *
from pyspark.sql.functions import *
from pyspark.sql.types import *
from src.main.utility.logging_config import *
import logging

logger = logging.getLogger(__name__)

def spark_session():
    spark = SparkSession.builder.master("local[*]") \
        .appName("bcv_de_project")\
        .config("spark.driver.extraClassPath", "C:\\my_sql_jar\\mysql-connector-java-8.0.30.jar") \
        .config("spark.hadoop.fs.file.impl.disable.cache", "true") \
        .config("spark.hadoop.io.native.lib.available", "false") \
        .config("spark.hadoop.native.io", "false") \
        .config("spark.hadoop.io.nativeio.NativeIO$Windows.access0", "false") \
        .config("spark.hadoop.fs.file.impl", "org.apache.hadoop.fs.LocalFileSystem") \
    .getOrCreate()
    logger.info("spark session %s", spark)
    spark.sparkContext.setLogLevel("INFO")
    return spark
