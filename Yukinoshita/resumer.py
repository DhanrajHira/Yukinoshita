from Yukinoshita.progress_tracker import ProgressTracker
from Yukinoshita.downloader import ChunkDownloader
from progress.bar import IncrementalBar

class Resumer(object):
    def __init__(self, resume_id, network):
        self.id = resume_id
        self.__network__ = network
        self.progress_tracker = ProgressTracker(resume_id)
        

    def resume(self):
        resume_data, chunks_done = self.progress_tracker.get_progress_data()
        chunk_tuple_list = resume_data["chunk_tuple_list"]
        decrypter_provider = resume_data["decrypter_provider"]
        total_chunks = resume_data["total_chunks"]
        self.progress_bar = IncrementalBar("Downloading", max=total_chunks)
        
        for _ in range(len(chunks_done)):
            #This loop updates the progress bar to show that chunks that were downloaded/
            self.progress_bar.next() 
        
        for chunk_number, chunk_tuple in enumerate(chunk_tuple_list):
            if chunk_number in chunks_done:
                continue
            else:
                file_name = f"chunks\/{resume_data['file_name']}-{chunk_number}.chunk.ts"
                ChunkDownloader(
                    self.__network__,
                    chunk_tuple[1], #Segment data
                    file_name,
                    chunk_tuple[0], #Chunk number
                    decrypter_provider
                ).download()
                self.progress_bar.next()
                self.progress_tracker.update_chunks_done(chunk_number)
            self.progress_bar.finish()