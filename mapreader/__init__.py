from mapreader.load.images import MapImages
from mapreader.load.loader import loader
from mapreader.load.loader import load_patches

from mapreader.download.sheet_downloader import SheetDownloader
from mapreader.download.downloader import Downloader
from mapreader.download.downloader_utils import create_polygon_from_latlons, create_line_from_latlons

from mapreader.classify.load_annotations import AnnotationsLoader
from mapreader.classify.datasets import PatchDataset
from mapreader.classify.datasets import PatchContextDataset
from mapreader.classify.classifier import ClassifierContainer
from mapreader.classify.classifier_context import ClassifierContextContainer
from mapreader.classify import custom_models

from mapreader.process import process

from . import _version

__version__ = _version.get_versions()["version"]

from mapreader.load import geo_utils
