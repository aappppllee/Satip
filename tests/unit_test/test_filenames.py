from satip.filenames import get_datetime_from_filename
import pandas as pd


def test_get_time_from_filename():

    datetime = get_datetime_from_filename("folder/iodc_202408281115.zarr.zip")
    assert datetime == pd.Timestamp("2024-08-28 11:15")

    datetime = get_datetime_from_filename("folder/202006011205.zarr.zip")
    assert datetime == pd.Timestamp("2020-06-01 12:05")

    datetime = get_datetime_from_filename("folder/hrv_202408261815.zarr.zip")
    assert datetime == "hrv_202408261815"

    datetime = get_datetime_from_filename("folder/15_hrv_202408261815.zarr.zip")
    assert datetime == "hrv_202408261815"
