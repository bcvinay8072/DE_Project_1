import datetime
import os
import shutil
from pyspark.sql.functions import *
from pyspark.sql.types import *
from http.client import responses

from resources.dev import config
from resources.dev.config import local_directory
from src.main.delete.local_file_delete import delete_local_file
from src.main.download.aws_file_download import S3FileDownloader
from src.main.move.move_files import move_s3_to_s3
from src.main.read.database_read import DatabaseReader
from src.main.transformations.jobs.customer_mart_sql_tranform_write import customer_mart_calculation_table_write
from src.main.transformations.jobs.dimension_tables_join import dimension_table_join
from src.main.transformations.jobs.sales_mart_sql_transform_write import sales_mart_calculation_table_write
from src.main.upload.upload_to_s3 import UploadToS3
from src.main.utility.encrypt_decrypt import *
from src.main.utility.my_sql_session import get_mysql_connection
from src.main.utility.s3_client_object import *
from src.main.utility.logging_config import *
from src.main.utility.my_sql_session import *
from src.main.read.aws_read import *
from src.main.utility.spark_session import spark_session
from src.main.write.parquet_writer import ParquetWriter
from src.test.generate_csv_data import sales_date
from src.test.scratch_pad import folder_path, s3_absolute_file_path

####################### Get S3 Client ######################
aws_access_key = config.aws_access_key
aws_secret_key = config.aws_secret_key

s3_client_provider = S3ClientProvider(decrypt(aws_access_key), decrypt(aws_secret_key))
s3_client = s3_client_provider.get_client()

# Now we can use S3
response = s3_client.list_buckets()
print(response)
logger.info("List of Buckets: %s", response['Buckets'])

csv_files = [file for file in os.listdir(config.local_directory) if file.endswith(".csv")]
connection = get_mysql_connection()
cursor = connection.cursor()

total_csv_files = []
if csv_files:
    for file in csv_files:
        total_csv_files.append(file)
    statement = f'''
    select distinct file_name 
    from DE_Project.product_staging_table
    where file_name in ({str(total_csv_files)[1:-1]}) and status='A'
    '''
    logger.info(f"Dynamically Statement Created: {statement}")
    cursor.execute(statement)
    data = cursor.fetchall()
    if data:
        logger.info("Your last run has failed please check !")
    else:
        logger.info("No records matched")
else:
    logger.info("Last run was successful !!")

try:
    s3_reader = S3Reader()
    # Bucket name should come from table
    folder_path = config.s3_source_directory
    s3_absolute_file_path = s3_reader.list_files(s3_client,
                                                 config.bucket_name,folder_path=folder_path)
    logger.info("Absolute path on s3 bucket for csv file %s ",s3_absolute_file_path)
    if not s3_absolute_file_path:
        logger.info(f"No files available at {folder_path}")
        raise Exception("No Data Available to process !")
except Exception as e:
    logger.error("Excited with error - %s",e)
    raise e

bucket_name = config.bucket_name
local_directory = config.local_directory

prefix = f"s3://{bucket_name}/"
file_paths = [url[len(prefix):] for url in s3_absolute_file_path]
logging.info("File path available on s3 under %s bucket and folder name is %s",bucket_name,file_paths)
try:
    downloader = S3FileDownloader(s3_client,bucket_name,local_directory)
    downloader.download_files(file_paths)
except Exception as e:
    logger.error("File download error: %s",e)
    sys.exit()

# Get all list of all files in the local directory
all_files = os.listdir(local_directory)
logger.info(f"List of files present at my local directory after download {all_files}")

# Filter files with ".csv" and create absolute paths

if all_files:
    csv_files=[]
    error_files = []
    for file in all_files:
        if file.endswith(".csv"):
            csv_files.append(os.path.abspath(os.path.join(local_directory, file)))
        else:
            error_files.append(os.path.abspath(os.path.join(local_directory, file)))
    if not csv_files:
        logger.error("No csv data available to process")
        raise Exception("No csv data available to process")
else:
    logger.error("There is no data to process")
    raise Exception("There is no data to process")

logger.info("***************** Listing the Files *****************")
logger.info("List of csv files that needs to be processed %s", csv_files)

logger.info("***************** Creating Spark Session *****************")
spark = spark_session()
logger.info("***************** Spark Session Created *****************")

'''
Check the required columns in the schema of csv files
if not required columns keep it in a list or error_files
else union all the data into one dataframe 

'''

logger.info("***************** Checking Schema for data loaded in S3 *****************")

correct_files = []
for data in csv_files:
    data_schema = spark.read.format("csv")\
                        .option("header","true")\
                        .load(data).columns
    logger.info(f"Schema for the {data} is {data_schema}")
    logger.info(f"Mandatory columns are {config.mandatory_columns}")
    missing_columns = set(config.mandatory_columns) - set(data_schema)
    logger.info(f"Missing columns are {missing_columns}")

    if missing_columns:
        error_files.append(data)
    else:
        logger.info(f"No missing column for the {data}")
        correct_files.append(data)

logger.info(f"***************** List of correct files *****************{correct_files}")
logger.info(f"***************** List of error files *****************{error_files}")
logger.info(f"***************** Moving Error data to error directory if any *****************")

# Move the data to error directory on local
error_folder_local_path = config.error_folder_path_local
if error_files:
    for file_path in error_files:
        if os.path.exists(file_path):
            file_name = os.path.basename(file_path)
            destination_path = os.path.join(error_folder_local_path, file_name)

            shutil.move(file_path, destination_path)
            logger.info(f"Moved '{file_name}' to '{destination_path}'")

            source_prefix = config.s3_source_directory
            destination_prefix = config.s3_error_directory

            message = move_s3_to_s3(s3_client,config.bucket_name,source_prefix,destination_prefix,file_name)
            logger.info(f"{message}")
        else:
            logger.error(f"'{file_path}' does not exist.")
else:
    logger.info("***************** There is no error files available in the dataset *****************")


'''
Additional columns needs to be taken care of 
Determine extra columns 

Before running the process 
Stage table needs to be updated with status as Active(A) or Inactive(I)
'''

logger.info(f"***************** Updating the product_staging_table that we have started the process *****************")
insert_statements = []
db_name = config.database_name
current_date = datetime.datetime.now()
formatted_date = current_date.strftime("%Y-%m-%d %H:%M:%S")
if correct_files:
    for file in correct_files:
        file_name = os.path.basename(file)
        statement = f'''
                    INSERT INTO {db_name}.{config.product_staging_table} (file_name, file_location, created_date, status) VALUES ('{file_name}', '{file_name}', '{formatted_date}', 'A')'''
        insert_statements.append(statement)
    logger.info(f"Insert statement created for staging table --- {insert_statements}")
    logger.info("***************** Connecting with MySQL server *****************")
    connection = get_mysql_connection()
    cursor = connection.cursor()
    logger.info("***************** MySQL server connected Successfully *****************")
    for statement in insert_statements:
        cursor.execute(statement)
        connection.commit()
    cursor.close()
    connection.close()
else:
    logger.error("***************** There are no files to process *****************")
    raise Exception("***************** No Data Available within correct files *****************")

logger.info("***************** Staging table updated successfully *****************")

logger.info("***************** Fixing extra column coming from source *****************")

schema = StructType([
    StructField("customer_id", IntegerType(), True),
    StructField("store_id", IntegerType(), True),
    StructField("product_name", StringType(), True),
    StructField("sales_date", DateType(), True),
    StructField("sales_person_id", IntegerType(), True),
    StructField("price", FloatType(), True),
    StructField("quantity", IntegerType(), True),
    StructField("total_cost", FloatType(), True),
    StructField("additional_column", StringType(), True)
])

logger.info("***************** Creating an empty Dataframe *****************")

final_df_to_process = spark.createDataFrame(spark.sparkContext.emptyRDD(), schema)

logger.info("***************** Schema of Empty Dataframe *****************")

final_df_to_process.show()

# Create a new column with concatenated values of extra columns
for data in correct_files:
    data_df = spark.read.format("csv")\
                    .option("header","true")\
                    .option("inferSchema","true")\
                    .load(data)
    data_schema = data_df.columns
    extra_columns = list(set(data_schema)-set(config.mandatory_columns))
    logger.info(f"Extra columns present at source is {extra_columns}")
    if extra_columns:
        data_df = data_df.withColumn("additional_column",
                                     concat_ws(", ",*extra_columns))\
                    .select("customer_id","store_id","product_name","sales_date","sales_person_id","price","quantity","total_cost","additional_column")
        logger.info(f"Processed {data} and added 'additional columns' !")
    else:
        data_df = data_df.withColumn("additional_column",lit(None)) \
            .select("customer_id", "store_id", "product_name", "sales_date", "sales_person_id", "price", "quantity","total_cost", "additional_column")
    final_df_to_process = final_df_to_process.union(data_df)

logger.info("***************** Final Dataframe from source which is going to be processed ! *****************")
final_df_to_process.show()

'''
Enrich the data from all dimension table
also create a datamart for sales_team and their incentive, address and all
another datamart for customer who bought, how many days of month
There should be a file for every month
Including store_id
Read the data from parquet and generate a csv file
Columns 👇👇 
sales_person_name, sales_person_store_id, sales_person_total_billing_done_for_each_month
total_incentive

'''

# Connecting to DatabaseReader
database_client = DatabaseReader(config.url, config.properties)
# Creating df for all tables
# Customer table
logger.info("***************** Loading customer table into customer_table_df *****************")
customer_table_df = database_client.create_dataframe(spark,config.customer_table_name)

# Product table
logger.info("***************** Loading product table into product_table_df *****************")
product_table_df = database_client.create_dataframe(spark,config.product_staging_table)

# Product_staging_table
logger.info("***************** Loading staging table into product_staging_table *****************")
sales_team_table_df = database_client.create_dataframe(spark,config.sales_team_table)

# Store table
logger.info("***************** Loading store table into store_table_df *****************")
store_table_df = database_client.create_dataframe(spark,config.store_table)

s3_customer_store_sales_df_join = dimension_table_join(final_df_to_process,
                                                       customer_table_df,
                                                       store_table_df,
                                                       sales_team_table_df)

# Final Enriched data
logger.info("***************** Final Enriched Data *****************")
s3_customer_store_sales_df_join.show()

'''
Write the customer data into customer data mart in parquet format
file will be written in local first
Move the RAW data to S3 Bucket for reporting tools
Write reporting data into MySQL table also

'''
logger.info("***************** Write the data into Customer Data Mart *****************")
final_customer_data_mart_df = s3_customer_store_sales_df_join\
                                .select("ct.customer_id","ct.first_name",
                                        "ct.last_name","ct.address","ct.pincode",
                                        "phone_number","sales_date","total_cost")
logger.info("***************** Final Data for customer Data Mart *****************")
final_customer_data_mart_df.show()

parquet_writer = ParquetWriter("overwrite","parquet")
parquet_writer.dataframe_writer(final_customer_data_mart_df,
                                config.customer_data_mart_local_file)

logger.info(f"***************** Customer Data written to local disk at {config.customer_data_mart_local_file} *****************")
# Move data to S3 bucket for customer_data_mart

logger.info("***************** Moving data from local to s3 for customer_data_mart *****************")
s3_uploader = UploadToS3(s3_client)
s3_directory = config.s3_customer_datamart_directory
message = s3_uploader.upload_to_s3(s3_directory,config.bucket_name,config.customer_data_mart_local_file)

logger.info(f"{message}")

# Sales team data mart

logger.info("***************** Writing data into sales_team_data_mart *****************")
final_sales_team_data_mart_df = s3_customer_store_sales_df_join\
                                .select("store_id","sales_person_id",
                                        "sales_person_first_name",
                                        "sales_person_last_name",
                                        "store_manager_name","manager_id",
                                        "is_manager","sales_person_address","sales_person_pincode",
                                        "sales_date","total_cost",
                                        expr("SUBSTRING(sales_date,1,7) as sales_month"))

logger.info("***************** Final Data for sales team Data Mart *****************")
final_sales_team_data_mart_df.show()
parquet_writer.dataframe_writer(final_sales_team_data_mart_df,config.sales_team_data_mart_local_file)
logger.info(f"Sales team data written to local disk at {config.sales_team_data_mart_local_file} *****************")

# Move data to S3 bucket for sales_data_mart
s3_directory = config.s3_sales_datamart_directory
message = s3_uploader.upload_to_s3(s3_directory,config.bucket_name,
                                   config.sales_team_data_mart_local_file)


logger.info(f"{message}")

# Also writing data into partitions
final_sales_team_data_mart_df.write.format("parquet")\
            .option("header","true")\
            .mode("overwrite")\
            .partitionBy("sales_month","store_id")\
            .option("path",config.sales_team_data_mart_partitioned_local_file)\
            .save()
# Move data to S3 for partitioned folder
s3_prefix = "sales_partitioned_data_mart"
current_epoch = int(datetime.datetime.now().timestamp()) * 1000
for root, dir, files in os.walk(config.sales_team_data_mart_partitioned_local_file):
    for file in files:
        local_file_path = os.path.join(root, file)
        relative_file_path = os.path.relpath(local_file_path,
                                             config.sales_team_data_mart_partitioned_local_file)
        s3_key = f"{s3_prefix}/{current_epoch}/{relative_file_path}"
        s3_client.upload_file(local_file_path, config.bucket_name, s3_key)


'''
Calculation for customer mart
Find out the customer total purchase every month
write the data into MySQL table

'''
logger.info("***************** Calculating every month purchase amount of customers *****************")
customer_mart_calculation_table_write(final_customer_data_mart_df)
logger.info("***************** Calculation of customer mart done and written into the table *****************")

'''
Calculation for sales team data mart
Find out total sales done by each sales person every month
Give the top performer 1% incentive of total sales 

'''

logger.info("***************** Calculating sales every month billed amount *****************")
sales_mart_calculation_table_write(final_sales_team_data_mart_df)
logger.info("***************** Calculation of sales mart done and written into the table *****************")

############################## LAST STEP ###################################
# Move the local files to S3 and delete local files
source_prefix = config.s3_source_directory
destination_prefix = config.s3_processed_directory
message = move_s3_to_s3(s3_client, config.bucket_name, source_prefix, destination_prefix)
logger.info(f"{message}")

logger.info("***************** Deleting sales data from local *****************")
delete_local_file(config.local_directory)
logger.info("***************** Deleted sales data from local *****************")

logger.info("***************** Deleting customer_data_mart data from local *****************")
delete_local_file(config.customer_data_mart_local_file)
logger.info("***************** Deleted customer_data_mart data from local *****************")

logger.info("***************** Deleting sales_team_data_mart data from local *****************")
delete_local_file(config.sales_team_data_mart_local_file)
logger.info("***************** Deleted sales_team_data_mart data from local *****************")

logger.info("***************** Deleting sales_team_data_mart_partitioned data from local *****************")
delete_local_file(config.sales_team_data_mart_partitioned_local_file)
logger.info("***************** Deleted sales_team_data_mart_partitioned data from local *****************")

# Updating the status of staging table
update_statements = []
if correct_files:
    for file in correct_files:
        filename = os.path.basename(file)
        statement = f"UPDATE {db_name}.{config.product_staging_table} "\
                    f"SET status = 'I', updated_date='{formatted_date}' "\
                    f"WHERE file_name = '{filename}'"
        update_statements.append(statement)
    logger.info(f"Updated statements created for staging table --- {update_statements}")
    logger.info("***************** Connecting MySQL Sever *****************")
    connection = get_mysql_connection()
    cursor = connection.cursor()
    logger.info("***************** MySQL server connected successfully *****************")
    for statement in update_statements:
        cursor.execute(statement)
        connection.commit()
    cursor.close()
    connection.close()
else:

    logger.error("***************** There is some error process in between *****************")
    sys.exit()


input("Press enter to terminate ")