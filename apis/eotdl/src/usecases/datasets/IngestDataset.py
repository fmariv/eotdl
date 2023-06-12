from pydantic import BaseModel
import typing

from ...models import Dataset, Usage, User, Limits
from ...errors import DatasetAlreadyExistsError, TierLimitError
from ...utils import calculate_checksum


class IngestDataset:
    def __init__(self, db_repo, os_repo):
        self.db_repo = db_repo
        self.os_repo = os_repo

    class Inputs(BaseModel):
        name: str
        description: str
        file: typing.Any
        size: int
        uid: str
        author: str
        link: str
        license: str
        tags: typing.List[str]

    class Outputs(BaseModel):
        dataset: Dataset

    async def __call__(self, inputs: Inputs) -> Outputs:
        # check if user can ingest dataset
        data = self.db_repo.retrieve("users", inputs.uid, "uid")
        user = User(**data)
        data = self.db_repo.find_one_by_name("tiers", user.tier)
        limits = Limits(**data["limits"])
        usage = self.db_repo.find_in_time_range(
            "usage", inputs.uid, "dataset_ingested", "type"
        )
        if len(usage) + 1 >= limits.datasets.upload:
            raise TierLimitError(
                "You cannot ingest more than {} datasets per day".format(
                    limits.datasets.upload
                )
            )
        # check if name already exists
        if self.db_repo.find_one_by_name("datasets", inputs.name):
            raise DatasetAlreadyExistsError()
        # generate new id
        id = self.db_repo.generate_id()
        # save file in storage
        self.os_repo.persist_file(inputs.file, id)
        # calculate checksum
        data_stream = self.os_repo.data_stream(id)
        checksum = await calculate_checksum(data_stream)
        print("checksum", checksum)
        # save dataset in db
        dataset = Dataset(
            uid=inputs.uid,
            id=id,
            name=inputs.name,
            description=inputs.description,
            size=inputs.size,
            author=inputs.author,
            link=inputs.link,
            license=inputs.license,
            tags=inputs.tags,
            checksum=checksum,
        )
        self.db_repo.persist("datasets", dataset.dict(), id)
        # update user dataset count
        self.db_repo.increase_counter("users", "uid", inputs.uid, "dataset_count")
        # report usage
        usage = Usage.DatasetIngested(uid=inputs.uid, payload={"dataset": id})
        self.db_repo.persist("usage", usage.dict())
        return self.Outputs(dataset=dataset)
