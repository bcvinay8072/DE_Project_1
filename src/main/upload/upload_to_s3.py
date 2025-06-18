import os
import traceback
import datetime
import platform
from src.main.utility.logging_config import *

class UploadToS3:
    def __init__(self, s3_client):
        self.s3_client = s3_client

    def upload_to_s3(self, s3_directory, s3_bucket, local_file_path):
        current_epoch = int(datetime.datetime.now().timestamp()) * 1000
        s3_prefix = f"{s3_directory}/{current_epoch}/"

        # Handle 'file://' prefix
        if local_file_path.startswith("file://"):
            local_file_path = local_file_path.replace("file://", "")
            if platform.system() == "Windows" and local_file_path.startswith("/"):
                local_file_path = local_file_path[1:]

        if not os.path.exists(local_file_path):
            logger.info(f"No files uploaded. Directory or file does not exist: {local_file_path}")
            return

        try:
            if os.path.isfile(local_file_path):
                filename = os.path.basename(local_file_path)
                s3_key = f"{s3_prefix}{filename}"
                self.s3_client.upload_file(local_file_path, s3_bucket, s3_key)
                logger.info(f"Uploaded file: {s3_key}")
            else:
                # It's a directory
                uploaded = False
                for root, dirs, files in os.walk(local_file_path):
                    for file in files:
                        full_path = os.path.join(root, file)
                        relative_path = os.path.relpath(full_path, local_file_path)
                        s3_key = f"{s3_prefix}{relative_path.replace(os.sep, '/')}"
                        self.s3_client.upload_file(full_path, s3_bucket, s3_key)
                        logger.info(f"Uploaded file: {s3_key}")
                        uploaded = True
                if not uploaded:
                    logger.info(f"No files uploaded. Directory empty: {local_file_path}")
            return f"Data successfully uploaded to s3://{s3_bucket}/{s3_prefix}"
        except Exception as e:
            logger.error(f"Error uploading to S3: {str(e)}")
            print(traceback.format_exc())
            raise e
