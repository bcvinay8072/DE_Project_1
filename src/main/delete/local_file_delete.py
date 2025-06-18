import os
import shutil
import traceback
import platform
from src.main.utility.logging_config import *

def delete_local_file(delete_file_path):
    try:
        # Handle file:// URI
        if delete_file_path.startswith("file://"):
            delete_file_path = delete_file_path.replace("file://", "")
            if platform.system() == "Windows" and delete_file_path.startswith("/"):
                delete_file_path = delete_file_path[1:]

        if not os.path.exists(delete_file_path):
            logger.warning(f"Path does not exist: {delete_file_path}")
            return

        files_to_delete = [os.path.join(delete_file_path, filename) for filename in os.listdir(delete_file_path)]

        for item in files_to_delete:
            if os.path.isfile(item):
                os.remove(item)
                logger.info(f"Deleted file: {item}")
            elif os.path.isdir(item):
                shutil.rmtree(item)
                logger.info(f"Deleted folder: {item}")

        logger.info(f"***************** Deleted data from local path: {delete_file_path} *****************")

    except Exception as e:
        logger.error(f"Error Deleting local files: {str(e)}")
        traceback_message = traceback.format_exc()
        logger.debug(traceback_message)
        print(traceback_message)
        raise e
