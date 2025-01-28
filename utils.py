import subprocess
from datetime import datetime

import exifread


def is_within_time_span(start_time, end_time, check_time=None):
    """
    Determines if a given time is within a time span.

    Args:
        start_time (time): The start of the time span.
        end_time (time): The end of the time span.
        check_time (time, optional): The time to check. Defaults to the current time.

    Returns:
        bool: True if the check_time is within the time span, False otherwise.
    """
    if check_time is None:
        check_time = datetime.now().time()

    # If the time span does not cross midnight
    if start_time <= end_time:
        return start_time <= check_time < end_time
    # If the time span crosses midnight
    else:
        return check_time >= start_time or check_time < end_time

def run_command(command, stdout=False, stderr=False):
    if type(command) == str:
        command = command.split(" ")
    print("DOWNLOADER: Running command", command)
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True)

        out, err, return_code = result.stdout.strip(" \n"), result.stderr.strip(" \n"), result.returncode == 0
    except Exception as e:
        out, err, return_code = "", str(e), False

    print("DOWNLOADER: Command done", command, return_code, out, err)
    if stdout and stderr:
        return return_code, out, err
    elif stdout:
        return return_code, out
    elif stderr:
        return return_code, err
    else:
        return return_code


def extract_date_from_exif(image_path):
    with open(image_path, 'rb') as image_file:
        tags = exifread.process_file(image_file)
        return tags.get("EXIF DateTimeOriginal")