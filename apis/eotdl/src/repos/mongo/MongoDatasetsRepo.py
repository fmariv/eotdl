from .MongoRepo import MongoRepo
from datetime import datetime


class MongoDatasetsRepo(MongoRepo):
    def __init__(self):
        super().__init__()

    def retrieve_datasets(self, name, limit):
        match = {}
        if name is not None:
            match = {"name": {"$regex": name, "$options": "i"}}
        return self.retrieve("datasets", limit=limit, match=match)

    def find_one_dataset_by_name(self, name):
        return self.find_one_by_name("datasets", name)

    def retrieve_dataset(self, dataset_id):
        return self.retrieve("datasets", dataset_id)

    def persist_files(self, files, id):
        return self.persist("files", files, id)

    def retrieve_files(self, id):
        return self.retrieve("files", id)

    def retrieve_file(self, files_id, file_id):
        # given the id of a file, retrieve it from the list of files
        return self.retrieve("files", id)

    def delete_files(self, id):
        return self.delete("files", id)

    def persist_dataset(self, dataset, id):
        return self.persist("datasets", dataset, id)

    def increase_user_dataset_count(self, uid):
        return self.increase_counter("users", "uid", uid, "dataset_count")

    def decrease_user_dataset_count(self, uid):
        return self.increase_counter("users", "uid", uid, "dataset_count", -1)

    def create_dataset_version(self, dataset, version):
        return self._update(
            "datasets",
            {"id": dataset.id},
            {
                "$set": {"updated_at": datetime.now()},
                "$push": {"versions": version},
            },
        )

    def update_dataset(self, dataset_id, dataset):
        return self.update("datasets", dataset_id, dataset)