from Yukinoshita.progress_tracker import ProgressTracker
from Yukinoshita.downloader import ChunkDownloader
from Yukinoshita.merger import FFmpegMerger, ChunkMerger, ChunkRemover
from progress.bar import IncrementalBar

class Resumer(object):
    def __init__(self, resume_id, network, use_ffmpeg=True, delete_chunks=True):
        self.id = resume_id
        self.__network__ = network
        self.use_ffmpeg = use_ffmpeg
        self.delete_chunks = delete_chunks
        self.progress_tracker = ProgressTracker(resume_id)

    def resume(self):
        resume_data, chunks_done = self.progress_tracker.get_progress_data()
        chunk_tuple_list = resume_data["chunk_tuple_list"]
        decrypter_provider = resume_data["decrypter_provider"]
        self.total_chunks = resume_data["total_chunks"]
        self.file_name  = resume_data["file_name"]
        self.progress_bar = IncrementalBar("Downloading", max=self.total_chunks)
        
        for _ in range(len(chunks_done)):
            #This loop updates the progress bar to show that chunks that were downloaded/
            self.progress_bar.next() 
        
        for chunk_number, chunk_tuple in enumerate(chunk_tuple_list):
            if chunk_number in chunks_done:
                continue
            else:
                file_name = f"chunks\/{self.file_name}-{chunk_number}.chunk.ts"
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

        def merge(self):
            if self.use_ffmpeg:
                merger = FFmpegMerger(self.file_name, self.total_chunks)
            else:
                merger = ChunkMerger(self.file_name, self.total_chunks)
            merger.merge()
            
            if self.delete_chunks:
                remover = ChunkRemover(self.file_name, self.total_chunks)
                remover.remove()
