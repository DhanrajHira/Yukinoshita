import pickle
import os

class ProgressTracker(object):
    def __init__(self, id):
        self.resume_data = None
        self.chunks_done = []
        self.id = id
        try:
            os.makedirs(f"chunks\/.temp-{id}")
        except FileExistsError:
            pass
    
    @property
    def resume_data_file_path(self):
        return f"chunks\/.temp-{self.id}\/.resume_data"

    @property
    def chunks_done_file_path(self):
        return f"chunks\/.temp-{self.id}\/.chunks_done"

    def init_tracker(self, resume_data):
        with open(self.resume_file_path, "wb") as resume_data_file:
            pickle.dump(resume_data, resume_data_file)
        with open(self.chunks_done_file_path, "wb") as chunks_done_file:
            pickle.dump(self.chunks_done, chunks_done_file)

    def update_chunks_done(self, chunk_done: int):
        with open(self.chunks_done_file_path, "rb") as chunks_done_file:
            read_chunks_done = pickle.load(chunks_done_file)
        self.chunks_done = read_chunks_done
        self.chunks_done.append(chunk_done)
        with open(self.chunks_done_file_path, "wb") as chunks_done_file:
            pickle.dump(self.chunks_done, chunks_done_file)

    def get_progress_data(self):
        try:
            with open(self.resume_data_file_path, "rb") as resume_data_file:
                resume_data = pickle.load(resume_data_file)
            with open(self.chunks_done_file_path, "rb") as chunks_done_file:
                chunks_done = pickle.load(chunks_done_file)
            return resume_data, chunks_done
        except:
            print("No data found!")
            return None

    def remove_data(self):
        os.remove(self.resume_data_file_path)
        os.remove(self.chunks_done_file_path)
