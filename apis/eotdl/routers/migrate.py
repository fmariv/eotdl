from fastapi import APIRouter, Depends
import logging
import os
from minio.commonconfig import CopySource
import hashlib
from boto3.s3.transfer import TransferConfig

from .auth import key_auth
from ..src.repos.mongo.client import get_db
from ..src.repos.minio.client import get_client
from ..src.repos.boto3.client import get_client as get_boto3_client
from ..src.repos.boto3 import Boto3Repo
from ..src.models import File, Files, Dataset, Version

from bson.objectid import ObjectId

router = APIRouter(prefix="/migrate", tags=["migrate"])
logger = logging.getLogger(__name__)

bucket = os.environ.get("S3_BUCKET")


@router.get("", include_in_schema=False)
def migrate_db(isAdmin: bool = Depends(key_auth)):
    # return "Done"
    db = get_db()
    collections = db.list_collection_names()
    s3 = get_client()
    boto = get_boto3_client()  # Boto3Repo()
    # create a backup of the changed collections
    collection_name = "datasets-bck"
    if not collection_name in collections:
        db[collection_name].insert_many(db["datasets"].find())
    # update datasets
    #   - create files
    #   - create version
    for dataset in db["datasets"].find():
        print("updating dataset", dataset["name"])
        size = dataset["size"]
        dataset_id = dataset["_id"]
        files_id = str(ObjectId())
        if dataset["quality"] == 0:
            files = []
            for f in dataset["files"]:
                files.append(
                    File(
                        name=f["name"],
                        size=f["size"],
                        checksum=f["checksum"],
                        version=1,
                        versions=[1],
                    )
                )
                new_object_name = f"{dataset_id}/{f['name']}.zip_1"
                # if size < 1024 * 1024 * 5:
                #     # minio errors when copying files larger than 5GB
                #     s3.copy_object(
                #         bucket, new_object_name, CopySource(bucket, f["name"])
                #     )
                # else:
                #     config = TransferConfig(multipart_threshold=5 * 1024 * 1024)  # 5Mb
                #     copy_source = {"Bucket": bucket, "Key": f["name"]}
                #     boto.copy(copy_source, bucket, new_object_name, Config=config)
            dataset["files"] = Files(
                id=files_id, dataset=dataset_id, files=files
            ).model_dump()
        version = Version(version_id=1, size=size).model_dump()
        dataset["version"] = [version]
        del dataset["files"]
        del dataset["size"]
        updated_dataset = Dataset(**dataset)
        db["datasets"].update_one({"_id": dataset_id}, {"$set": updated_dataset})
    return "Done"
