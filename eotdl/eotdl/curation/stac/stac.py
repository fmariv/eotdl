"""
Module for generating STAC metadata 
"""

from typing import Union
import pandas as pd
import json
import pystac
from random import sample
from tqdm import tqdm

from os import listdir
from os.path import join, basename, exists, dirname
from shutil import rmtree

import rasterio
from rasterio.warp import transform_bounds

from datetime import datetime
from shapely.geometry import Polygon, mapping
from glob import glob

from .parsers import STACIdParser, StructuredParser
from .assets import STACAssetGenerator
from .utils import format_time_acquired, count_ocurrences
from .extensions import type_stac_extensions_dict, SUPPORTED_EXTENSIONS, LabelExtensionObject


class STACGenerator:
        
    def __init__(self, 
                 image_format: str='tiff',
                 catalog_type: pystac.CatalogType=pystac.CatalogType.SELF_CONTAINED,
                 item_parser: STACIdParser=StructuredParser,
                 assets_generator: STACAssetGenerator=STACAssetGenerator
                 ) -> None:
        """
        Initialize the STAC generator
        
        :param image_format: image format of the assets
        :param catalog_type: type of the catalog
        :param item_parser: parser to get the item ID
        :param assets_generator: generator to generate the assets
        """
        self._image_format = image_format
        self._catalog_type = catalog_type
        self._item_parser = item_parser()
        self._assets_generator = assets_generator()
        self._extensions_dict: dict = type_stac_extensions_dict
        self._stac_dataframe = pd.DataFrame()

    def generate_stac_metadata(self,
                               id: str,
                               description: str,
                               stac_dataframe: pd.DataFrame = None,
                               output_folder: str='stac',
                               kwargs: dict={}) -> None:
        """
        Generate STAC metadata for a given directory containing the assets to generate metadata

        :param stac_dataframe: dataframe with the STAC metadata of a given directory containing the assets to generate metadata
        :param id: id of the catalog
        :param description: description of the catalog
        :param output_folder: output folder to write the catalog to
        """
        self._stac_dataframe = stac_dataframe if self._stac_dataframe.empty else self._stac_dataframe
        if self._stac_dataframe.empty:
            raise ValueError('No STAC dataframe provided')
        
        # Create an empty catalog
        catalog = self.create_stac_catalog(id=id, description=description)
        
        # Add the collections to the catalog
        collections = self._stac_dataframe.collection.unique()
        for collection_path in collections:
            # TODO check if the items are directly under the root directory
            # Generate the collection
            collection = self.generate_stac_collection(collection_path)
            # Add the collection to the catalog
            catalog.add_child(collection)
        
        # Add the catalog to the root directory
        catalog.normalize_hrefs(output_folder)

        # Validate the catalog
        print('Validating and saving catalog...')
        try:
            pystac.validation.validate(catalog)
            catalog.save(catalog_type=self._catalog_type)
            print('Success!')
        except pystac.STACValidationError as e:
            print(f'Catalog validation error: {e}')
            return
        
    def cut_images(self, images_list: list|tuple) -> list:
        """
        # TODO poner en otro archivo
        
        """
        dirnames = list()
        images = list()

        for image in images_list:
            dir = dirname(image)
            if dir not in dirnames:
                dirnames.append(dir)
                images.append(image)

        return images

    def get_stac_dataframe(self, 
                           path: str, 
                           collections: str|dict='source',
                           bands: dict=None, 
                           extensions: dict=None
                           ) -> pd.DataFrame:
        """
        Get a dataframe with the STAC metadata of a given directory containing the assets to generate metadata

        :param path: path to the root directory
        :param extensions: dictionary with the extensions
        :param image_format: image format of the assets
        """
        images = glob(str(path) + f'/**/*.{self._image_format}', recursive=True)
        if self._assets_generator.type == 'Extracted':
            images = self.cut_images(images)

        labels, ixs = self._format_labels(images)
        bands_values = self._get_items_list_from_dict(labels, bands)
        extensions_values = self._get_items_list_from_dict(labels, extensions)

        if collections == 'source':
            # List of path with the same value repeated as many times as the number of images
            collections_values = [join(path, 'source') for i in range(len(images))]
        else:
            try:
                collections_values = [join(path, value) for value in self._get_items_list_from_dict(labels, collections)]
            except TypeError as e:
                # TODO control this error
                raise TypeError(f'Control this error')

        df = pd.DataFrame({'image': images, 
                           'label': labels, 
                           'ix': ixs, 
                           'collection': collections_values, 
                           'extensions': extensions_values, 
                           'bands': bands_values
                           })
        
        self._stac_dataframe = df
        
        return df
    
    def _get_images_common_prefix(self, images: list) -> list:
        """
        Get the common prefix of a list of images

        :param images: list of images
        """
        images_common_prefix_dict = dict()

        images_dirs = [dirname(i) for i in images]

        for image in images_dirs:
            path = image
            common = False
            while not common:
                n = count_ocurrences(path, images_dirs)
                if n > 1:
                    images_common_prefix_dict[image] = path
                    common = True
                else:
                    path = dirname(path)

        images_common_prefix_list = list()
        for i in images:
            images_common_prefix_list.append(images_common_prefix_dict[dirname(i)])

        return images_common_prefix_list
    
    def _format_labels(self, images):
        """
        Format the labels of the images

        :param images: list of images
        """
        labels = [x.split('/')[-1].split('_')[0].split('.')[0] for x in images]
        ixs = [labels.index(x) for x in labels]
        return labels, ixs
    
    def _get_items_list_from_dict(self, labels: list, items: dict) -> list:
        """
        Get a list of items from a dictionary

        :param labels: list of labels
        :param items: dictionary with the items
        """
        if not items:
            # Create list of None with the same length as the labels list
            return [None for _ in labels]
        items_list = list()
        for label in labels:
            if label in items.keys():
                items_list.append(items[label])
            else:
                items_list.append(None)

        return items_list
    
    def _get_collection_extent(self, rasters: list[str]) -> pystac.Extent:
        """
        Get the extent of a collection
        
        :param path: path to the directory
        """
        # Get the spatial extent of the collection
        spatial_extent = self._get_collection_spatial_extent(rasters)
        # Get the temporal interval of the collection
        temporal_interval = self._get_collection_temporal_interval(rasters)
        # Create the Extent object
        extent = pystac.Extent(spatial=spatial_extent, temporal=temporal_interval)

        return extent
    
    def _get_collection_spatial_extent(self, rasters: list[str]) -> pystac.SpatialExtent:
        """
        Get the spatial extent of a collection

        :param path: path to the directory
        """
        # Get the bounding boxes of all the given rasters
        bboxes = list()
        for raster in rasters:
            with rasterio.open(raster) as ds:
                bounds = ds.bounds
                dst_crs = 'EPSG:4326'
                try:
                    left, bottom, right, top = rasterio.warp.transform_bounds(ds.crs, dst_crs, *bounds)
                    bbox = [left, bottom, right, top]
                except rasterio.errors.CRSError:
                    spatial_extent = pystac.SpatialExtent([[0, 0, 0, 0]])
                    return spatial_extent
                bboxes.append(bbox)
        # Get the minimum and maximum values of the bounding boxes
        try:
            left = min([bbox[0] for bbox in bboxes])
            bottom = min([bbox[1] for bbox in bboxes])
            right = max([bbox[2] for bbox in bboxes])
            top = max([bbox[3] for bbox in bboxes])
            spatial_extent = pystac.SpatialExtent([[left, bottom, right, top]])
        except ValueError:
            spatial_extent = pystac.SpatialExtent([[0, 0, 0, 0]])
        finally:
            return spatial_extent
    
    def _get_collection_temporal_interval(self, rasters: list[str]) -> pystac.TemporalExtent:
        """
        Get the temporal interval of a collection

        :param path: path to the directory
        """
        # Get all the metadata.json files in the directory of all the given rasters
        metadata_json_files = list()
        for raster in rasters:
            metadata_json_files += glob(f'{dirname(raster)}/*.json', recursive=True)

        if not metadata_json_files:
            return self._get_unknow_temporal_interval()   # If there is no metadata, set a generic temporal interval
        
        # Get the temporal interval of every metadata.json file and the type of the data
        data_types = list()
        temporal_intervals = list()
        for metadata_json_file in metadata_json_files:
            with open(metadata_json_file, 'r') as f:
                metadata = json.load(f)
            # Append the temporal interval to the list as a datetime object
            temporal_intervals.append(metadata['date-adquired']) if metadata['date-adquired'] else None
            # Append the data type to the list
            data_types.append(metadata['type']) if metadata['type'] else None
            
        if temporal_intervals:
            try:
                # Get the minimum and maximum values of the temporal intervals
                min_date = min([datetime.strptime(interval, '%Y-%m-%d') for interval in temporal_intervals])
                max_date = max([datetime.strptime(interval, '%Y-%m-%d') for interval in temporal_intervals])
            except ValueError:
                min_date = datetime.strptime('2000-01-01', '%Y-%m-%d')
                max_date = datetime.strptime('2023-12-31', '%Y-%m-%d')
            finally:
                # Create the temporal interval
                return pystac.TemporalExtent([(min_date, max_date)])
        else:
            # Check if the collection is composed by DEM data. If not, set a generic temporal interval
            if set(data_types) == {'dem'} or set(data_types) == {'DEM'} or set(data_types) == {'dem', 'DEM'}:
                return self._get_dem_temporal_interval()
            else:
                return self._get_unknow_temporal_interval()
            
    def _get_dem_temporal_interval(self) -> pystac.TemporalExtent:
        """
        Get a temporal interval for DEM data
        """
        min_date = datetime.strptime('2011-01-01', '%Y-%m-%d')
        max_date = datetime.strptime('2015-01-07', '%Y-%m-%d')

        return pystac.TemporalExtent([(min_date, max_date)])
    
    def _get_unknow_temporal_interval(self) -> pystac.TemporalExtent:
        """
        Get an unknown temporal interval
        """
        min_date = datetime.strptime('2000-01-01', '%Y-%m-%d')
        max_date = datetime.strptime('2023-12-31', '%Y-%m-%d')

        return pystac.TemporalExtent([(min_date, max_date)])
    
    def _get_unknow_extent(self) -> pystac.Extent:
        """
        """
        return pystac.Extent(spatial=pystac.SpatialExtent([[0, 0, 0, 0]]),
                                   temporal=pystac.TemporalExtent([(datetime.strptime('2000-01-01', '%Y-%m-%d'), 
                                                                    datetime.strptime('2023-12-31', '%Y-%m-%d'))]))

    def create_stac_catalog(self, id: str, description: str, kwargs: dict={}) -> pystac.Catalog:
        """
        Create a STAC catalog

        :param id: id of the catalog
        :param description: description of the catalog
        :param params: additional parameters
        """
        return pystac.Catalog(id=id, description=description, **kwargs)

    def generate_stac_collection(self, collection_path: str) -> pystac.Collection:
        """
        Generate a STAC collection from a directory containing the assets to generate metadata

        :param path: path to the root directory
        """
        # Get the images of the collection, as they are needed to obtain the collection extent
        collection_images = self._stac_dataframe[self._stac_dataframe['collection'] == collection_path]['image']
        # Get the collection extent
        extent = self._get_collection_extent(collection_images)
        # Create the collection
        collection_id = basename(collection_path)
        collection = pystac.Collection(id=collection_id,
                                        description='Collection',
                                        extent=extent)
        
        print(f'Generating {collection_id} collection...')
        for image in tqdm(collection_images):
            # Create the item
            item = self.create_stac_item(image)
            # Add the item to the collection
            collection.add_item(item)

        # Return the collection
        return collection

    def create_stac_item(self,
                        raster_path: str,
                        kwargs: dict={}
                        ) -> pystac.Item:
        """
        Create a STAC item from a directory containing the raster files and the metadata.json file

        :param raster_path: path to the raster file
        """
        # Check if there is any metadata file in the directory associated to the raster file
        metadata = self._get_item_metadata(raster_path)

        # Obtain the bounding box from the raster
        with rasterio.open(raster_path) as ds:
            bounds = ds.bounds
            dst_crs = 'EPSG:4326'
            try:
                left, bottom, right, top = rasterio.warp.transform_bounds(ds.crs, dst_crs, *bounds)
            except rasterio.errors.CRSError:
                # If the raster has no crs, set the bounding box to 0
                left, bottom, right, top = 0, 0, 0, 0

        # Create bbox
        bbox = [left, bottom, right, top]

        # Create geojson feature
        # If the bounding box has no values, set the geometry to None
        geom = mapping(Polygon([
            [left, bottom],
            [left, top],
            [right, top],
            [right, bottom]
        ]))

        # Initialize pySTAC item parameters
        params = dict()
        params['properties'] = dict()

        # Obtain the date acquired
        start_time, end_time = None, None
        if metadata and metadata["date-adquired"] and metadata["type"] not in ('dem', 'DEM'):
            time_acquired = format_time_acquired(metadata["date-adquired"])
        else:
            # Check if the type of the data is DEM
            if metadata and metadata["type"] and metadata["type"] in ('dem', 'DEM'):
                time_acquired = None
                start_time = datetime.strptime('2011-01-01', '%Y-%m-%d')
                end_time = datetime.strptime('2015-01-07', '%Y-%m-%d')
                params['start_datetime'] = start_time
                params['end_datetime'] = end_time
            else:
                # Set unknown date
                time_acquired = datetime.strptime('2000-01-01', '%Y-%m-%d')

        # Obtain the item ID. The approach depends on the item parser
        id = self._item_parser.get_item_id(raster_path)
        
        # Instantiate pystac item
        item = pystac.Item(id=id,
                geometry=geom,
                bbox=bbox,
                datetime=time_acquired,
                **params)
        
        # Get the item info, from the raster path
        item_info = self._stac_dataframe[self._stac_dataframe['image'] == raster_path]
        # Get the extensions of the item
        extensions = item_info['extensions'].values
        extensions = extensions[0] if extensions else None

        # Add the required extensions to the item
        if extensions:
            if isinstance(extensions, str):
                extensions = [extensions]
            for extension in extensions:
                if extension not in SUPPORTED_EXTENSIONS:
                    raise ValueError(f'Extension {extension} not supported')
                else:
                    extension_obj = self._extensions_dict[extension]
                    extension_obj.add_extension_to_object(item, item_info)

        # Add the assets to the item
        assets = self._assets_generator.extract_assets(item_info)
        if not assets:
            # If there are not assets using the selected generator, try with the default
            assets = STACAssetGenerator.extract_assets(item_info)

        # Add the assets to the item
        if assets:
            for asset in assets:
                if isinstance(asset, pystac.Asset):
                    item.add_asset(asset.title, asset)
                    # Add the required extensions to the asset if required
                    if extensions:
                        if isinstance(extensions, str):
                            extensions = [extensions]
                        for extension in extensions:
                            if extension not in SUPPORTED_EXTENSIONS:
                                raise ValueError(f'Extension {extension} not supported')
                            else:
                                extension_obj = self._extensions_dict[extension]
                                extension_obj.add_extension_to_object(asset, item_info)

        item.set_self_href(join(dirname(raster_path), f'{id}.json'))
        item.make_asset_hrefs_relative()
        
        return item

    def _get_item_metadata(self, raster_path: str) -> str:
        """
        Get the metadata JSON file of a given directory, associated to a raster file

        :param raster_path: path to the raster file
        """
        # Get the directory of the raster file
        raster_dir_path = dirname(raster_path)
        # Get the metadata JSON file
        # Check if there is a metadata.json file in the directory
        if 'metadata.json' in listdir(raster_dir_path):
            metadata_json = join(raster_dir_path, 'metadata.json')
        else:
            # If there is no metadata.json file in the directory, check if there is
            # a json file with the same name as the raster file
            raster_name = raster_path.split('/')[-1]
            raster_name = raster_name.split('.')[0]
            metadata_json = join(raster_dir_path, f'{raster_name}.json')
            if not exists(metadata_json):
                # If there is no metadata.json file in the directory, return None
                return None
        
        # Open the metadata.json file and return it
        with open(metadata_json, 'r') as f:
            metadata = json.load(f)
        
        return metadata

    def generate_stac_labels(self,
                             catalog: pystac.Catalog|str,
                             stac_dataframe: pd.DataFrame = None,
                             collection: pystac.Collection|str = None
                             ) -> None:
        """
        """
        self._stac_dataframe = stac_dataframe if self._stac_dataframe.empty else self._stac_dataframe
        if self._stac_dataframe.empty:
            raise ValueError('No STAC dataframe provided, please provide a STAC dataframe or generate it with <get_stac_dataframe> method')
        if isinstance(catalog, str):
            catalog = pystac.Catalog.from_file(catalog)

        # Add the labels collection to the catalog
        # If exists a source collection, get it extent
        source_collection = catalog.get_child('source')
        if source_collection:
            extent = source_collection.extent
            source_items = source_collection.get_all_items()
        else:
            if not collection:
                raise ValueError('No source collection provided, please provide a source collection')
            extent = self._get_unknow_extent()
        
        # Create the labels collection and add it to the catalog if it does not exist
        # If it exists, remove it
        collection = pystac.Collection(id='labels',
                                        description='Labels',
                                        extent=extent)
        if collection.id in [c.id for c in catalog.get_children()]:
            catalog.remove_child(collection.id)
        catalog.add_child(collection)

        # Generate the labels items
        print('Generating labels collection...')
        for source_item in tqdm(source_items):
            source_item.make_asset_hrefs_absolute()
            # Get assets hrefs
            assets = source_item.assets
            assets_hrefs = [assets[asset].href for asset in assets]
            # Supose the first asset href is enough if assets_hrefs is a list
            asset_href = assets_hrefs[0] if isinstance(assets_hrefs, list) else assets_hrefs
            # Restore the relative paths
            source_item.make_asset_hrefs_relative()
            # Get the label of the item
            label = self._stac_dataframe[self._stac_dataframe['image'] == asset_href]['label'].values[0]
            # Create the label item
            # TODO put kwargs
            label_item = LabelExtensionObject.add_extension_to_item(source_item,
                                                                      href=asset_href,
                                                                      label_names=['label'],
                                                                      label_classes=[[label]],
                                                                      label_properties=['label'],
                                                                      label_description='Item label',
                                                                      label_methods=['manual'],
                                                                      label_tasks=['classification'],
                                                                      label_type='vector')

            collection.add_item(label_item)

        # Add the extension to the collection
        # TODO put in kwargs
        LabelExtensionObject.add_extension_to_collection(collection,
                                                         label_names=['label'],
                                                         label_classes=[self._stac_dataframe.label.unique().tolist()],
                                                         label_type='vector')

        # Validate and save the catalog
        try:
            pystac.validation.validate(catalog)
            catalog.save(catalog_type=self._catalog_type)
        except pystac.STACValidationError as e:
            print(f'Catalog validation error: {e}')
            return


def merge_stac_catalogs(catalog_1: pystac.Catalog|str,
                        catalog_2: pystac.Catalog|str,
                        destination: str = None,
                        keep_extensions: bool = False,
                        catalog_type: pystac.CatalogType = pystac.CatalogType.SELF_CONTAINED
                        ) -> None:
    """
    """
    if isinstance(catalog_1, str):
        catalog_1 = pystac.Catalog.from_file(catalog_1)
    if isinstance(catalog_2, str):
        catalog_2 = pystac.Catalog.from_file(catalog_2)

    for col1 in tqdm(catalog_1.get_children(), desc='Merging catalogs...'):
        # Check if the collection exists in catalog_2
        col2 = catalog_2.get_child(col1.id)
        if col2 is None:
            # If it does not exist, add it
            col1_ = col1.clone()
            catalog_2.add_child(col1)
            col2 = catalog_2.get_child(col1.id)
            col2.clear_items()
            for i in col1_.get_all_items():
                col2.add_item(i)
        else:
            # If it exists, merge the items
            for item1 in col1.get_items():
                if col2.get_item(item1.id) is None:
                    col2.add_item(item1)

    if keep_extensions:
        for ext in catalog_1.stac_extensions:
            if ext not in catalog_2.stac_extensions:
                catalog_2.stac_extensions.append(ext)

        for extra_field_name, extra_field_value in catalog_1.extra_fields.items():
            if extra_field_name not in catalog_2.extra_fields:
                catalog_2.extra_fields[extra_field_name] = extra_field_value

    if not destination:
        destination = dirname(catalog_2.get_self_href())
        rmtree(destination)   # Remove the old catalog and replace it with the new one
    # Save the merged catalog
    print('Validating...')
    catalog_2.normalize_and_save(destination, catalog_type)
    print('Success')