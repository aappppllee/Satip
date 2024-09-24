""" Function to do with filenames """
import pandas as pd


def get_datetime_from_filename(filename: str) -> pd.Timestamp:
    """Extract time from filename

    For example:
    - folder/iodc_202408281115.zarr.zip
    - folder/202006011205.zarr.zip
    - folder/hrv_202408261815.zarr.zip
    - folder/15_hrv_202408261815.zarr.zip
    """

    filename = filename.replace("iodc_", "")
    filename = filename.replace("15_", "")
    filename = filename.split(".zarr.zip")[0]
    date = filename.split("/")[-1]

    file_time = pd.to_datetime(
        date,
        format="%Y%m%d%H%M",
        errors="ignore",
        utc=True,
    )
    return file_time
