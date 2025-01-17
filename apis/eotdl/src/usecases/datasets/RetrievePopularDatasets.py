from pydantic import BaseModel
import typing
from typing import List, Union

from ...models import Dataset

class RetrievePopularDatasets():
    def __init__(self, db_repo):
        self.db_repo = db_repo

    class Inputs(BaseModel):
        limit: Union[int,None] = None

    class Outputs(BaseModel):
        datasets: List[Dataset]

    def __call__(self, inputs: Inputs) -> Outputs:
        data = self.db_repo.find_top('datasets', 'likes', inputs.limit)
        datasets = [Dataset(**d) for d in data]
        return self.Outputs(datasets=datasets)