# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/05_pipeline.ipynb (unless otherwise specified).

__all__ = ['user_key', 'user_secret', 'slack_id', 'slack_webhook_url', 'download_eumetsat_files',
           'df_metadata_to_dt_to_fp_map', 'reproject_datasets', 'compress_and_save_datasets', 'save_metadata',
           'compress_export_then_delete_raw', 'download_latest_data_pipeline', 'download_missing_eumetsat_files',
           'download_missing_data_pipeline']

# Cell
import pandas as pd
import xarray as xr

from satip import eumetsat, reproj, io, gcp_helpers
from dagster import execute_pipeline, pipeline, solid, Field

import os
import dotenv

# Cell
user_key = os.environ.get('USER_KEY')
user_secret = os.environ.get('USER_SECRET')
slack_id = os.environ.get('SLACK_ID')
slack_webhook_url = os.environ.get('SLACK_WEBHOOK_URL')

# Cell
@solid(
    config_schema = {
        'user_key': Field(str, default_value=user_key, is_required=False),
        'user_secret': Field(str, default_value=user_secret, is_required=False),
        'slack_webhook_url': Field(str, default_value=slack_webhook_url, is_required=False),
        'slack_id': Field(str, default_value=slack_id, is_required=False)
    }
)
def download_eumetsat_files(context, data_dir: str, metadata_db_fp: str, debug_fp: str, table_id: str, project_id: str, start_date: str='', end_date: str=''):
    if start_date == '':
        sql_query = f'select * from {table_id} where result_time = (select max(result_time) from {table_id})'
        start_date = gcp_helpers.query(sql_query, project_id)['result_time'].iloc[0]

    if end_date == '':
        end_date = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')

    dm = eumetsat.DownloadManager(context.solid_config['user_key'], context.solid_config['user_secret'], data_dir, metadata_db_fp, debug_fp, slack_webhook_url=context.solid_config['slack_webhook_url'], slack_id=context.solid_config['slack_id'])
    df_new_metadata = dm.download_date_range(start_date, end_date)

    if df_new_metadata is None:
        df_new_metadata = pd.DataFrame(columns=['result_time', 'file_name'])
    else:
        df_new_metadata = df_new_metadata.iloc[1:] # the first entry is the last one we downloaded

    return df_new_metadata

@solid()
def df_metadata_to_dt_to_fp_map(_, df_new_metadata, data_dir: str) -> dict:
    """
    Here we'll then identify downloaded files in
    the metadata dataframe and return a mapping
    between datetimes and filenames
    """

    datetime_to_filename = (df_new_metadata
                            .set_index('result_time')
                            ['file_name']
                            .drop_duplicates()
                            .to_dict()
                           )

    datetime_to_filepath = {
        datetime: f"{data_dir}/{filename}.nat"
        for datetime, filename
        in datetime_to_filename.items()
        if filename != {}
    }

    return datetime_to_filepath

@solid()
def reproject_datasets(_, datetime_to_filepath: dict, new_coords_fp: str, new_grid_fp: str):
    reprojector = reproj.Reprojector(new_coords_fp, new_grid_fp)

    reprojected_dss = [
        (reprojector
         .reproject(filepath, reproj_library='pyresample')
         .pipe(io.add_constant_coord_to_da, 'time', pd.to_datetime(datetime))
        )
        for datetime, filepath
        in datetime_to_filepath.items()
    ]

    if len(reprojected_dss) > 0:
        ds_combined_reproj = xr.concat(reprojected_dss, 'time', coords='all', data_vars='all')
        return ds_combined_reproj
    else:
        return xr.Dataset()

@solid()
def compress_and_save_datasets(_, ds_combined_reproj, zarr_bucket: str, var_name: str='stacked_eumetsat_data'):
    # Handle case where no new data exists
    if len(ds_combined_reproj.dims) == 0:
        return

    # Compressing the datasets
    compressor = io.Compressor()

    var_name = var_name
    da_compressed = compressor.compress(ds_combined_reproj[var_name])

    # Saving to Zarr
    ds_compressed = io.save_da_to_zarr(da_compressed, zarr_bucket)

    return ds_compressed

@solid()
def save_metadata(context, ds_combined_compressed, df_new_metadata, table_id: str, project_id: str):
    if ds_combined_compressed is not None:
        if df_new_metadata.shape[0] > 0:
            gcp_helpers.write_metadata_to_gcp(df_new_metadata, table_id, project_id, append=True)
            context.log.info(f'{df_new_metadata.shape[0]} new metadata entries were added')
        else:
            context.log.info('No metadata was available to be added')

@solid()
def compress_export_then_delete_raw(context, ds_combined_compressed, data_dir: str, compressed_dir: str, BUCKET_NAME: str='solar-pv-nowcasting-data', PREFIX: str='satellite/EUMETSAT/SEVIRI_RSS/native/'):
    if ds_combined_compressed is not None:
        compress_downloaded_files(data_dir=data_dir, compressed_dir=compressed_dir, log=context.log)
        upload_compressed_files(compressed_dir, BUCKET_NAME=BUCKET_NAME, PREFIX=PREFIX, log=None)

        for dir_ in [data_dir, compressed_dir]:
            files = glob.glob(f'{dir_}/*')

            for f in files:
                os.remove(f)

# Cell
@pipeline
def download_latest_data_pipeline():
    # Retrieving data, reprojecting, compressing, and saving to GCP
    df_new_metadata = download_eumetsat_files()
    datetime_to_filepath = df_metadata_to_dt_to_fp_map(df_new_metadata)
    ds_combined_reproj = reproject_datasets(datetime_to_filepath)
    ds_combined_compressed = compress_and_save_datasets(ds_combined_reproj)

    save_metadata(ds_combined_compressed, df_new_metadata)
    compress_export_then_delete_raw(ds_combined_compressed)

# Cell
@solid(
    config_schema = {
        'user_key': Field(str, default_value=user_key, is_required=False),
        'user_secret': Field(str, default_value=user_secret, is_required=False),
        'slack_webhook_url': Field(str, default_value=slack_webhook_url, is_required=False),
        'slack_id': Field(str, default_value=slack_id, is_required=False)
    }
)
def download_missing_eumetsat_files(context, data_dir: str, metadata_db_fp: str, debug_fp: str, table_id: str, project_id: str, start_date: str='', end_date: str=''):
    dm = eumetsat.DownloadManager(context.solid_config['user_key'], context.solid_config['user_secret'], data_dir, metadata_db_fp, debug_fp, slack_webhook_url=context.solid_config['slack_webhook_url'], slack_id=context.solid_config['slack_id'])

    missing_datasets = io.identifying_missing_datasets(start_date, end_date)[:5]
    df_new_metadata = dm.download_datasets(missing_datasets)

    if df_new_metadata is None:
        df_new_metadata = pd.DataFrame(columns=['result_time', 'file_name'])
    else:
        df_new_metadata = df_new_metadata.iloc[1:] # the first entry is the last one we downloaded

    return df_new_metadata

# Cell
@pipeline
def download_missing_data_pipeline():
    # Retrieving data, reprojecting, compressing, and saving to GCP
    df_new_metadata = download_missing_eumetsat_files()
    datetime_to_filepath = df_metadata_to_dt_to_fp_map(df_new_metadata)
    ds_combined_reproj = reproject_datasets(datetime_to_filepath)
    ds_combined_compressed = compress_and_save_datasets(ds_combined_reproj)

    save_metadata(ds_combined_compressed, df_new_metadata)
    compress_export_then_delete_raw(ds_combined_compressed)