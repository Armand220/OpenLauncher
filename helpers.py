import os
import shutil
import time
import zipfile

def is_valid_jar(filepath):
    if not os.path.isfile(filepath):
        return False
    try:
        with zipfile.ZipFile(filepath, 'r') as zf:
            if zf.testzip() is not None:
                return False
        return True
    except:
        return False

def copy_file_with_retry(src, dst, max_attempts=5, delay=0.5):
    if os.path.abspath(src) == os.path.abspath(dst):
        return True
    for attempt in range(max_attempts):
        try:
            shutil.copy2(src, dst)
            return True
        except (PermissionError, OSError):
            if attempt == max_attempts - 1:
                raise
            time.sleep(delay)
    return False