import os
from threading import Thread, Lock
from progress.bar import IncrementalBar
from Yukinoshita.progress_tracker import ProgressTracker
from Yukinoshita.decrypter_provider import DecrypterProvider
from concurrent.futures import ThreadPoolExecutor

class Downloader(object):
    """
    Facilitates downloading an episode from aniwatch.me using a single thread.

    """
    def __init__(
        self,
        network,
        m3u8,
        file_name: str,
        id: int,
        use_ffmpeg: bool = True,
        delete_chunks: bool = True,
        hooks = {},
    ):
        self.__network__ = network
        self.m3u8 = m3u8
        self.file_name = file_name
        self.id = id
        self.use_ffmpeg = use_ffmpeg
        self.delete_chunks = delete_chunks
        self.hooks = hooks
        self.progress_tracker = ProgressTracker(id)

    def init_tracker(self):
        self.progress_tracker.init_tracker(
            {
                "headers": None,
                "cookies": None,
                "segments": self.m3u8.data["segments"],
                "file_name": self.file_name,
                "total_chunks": self.total_chunks,
            }
        )

    def download(self):
        chunk_tuple_list = []
        # Will hold a list of tuples of the form (chunk_number, chunk).
        # The chunk_number in this list will start from 1.
        for chunk_number, chunk in enumerate(self.m3u8.data["segments"]):
            chunk_tuple_list.append((chunk_number, chunk))

        if self.hooks.get("modify_chunk_tuple_list", None) is not None:
            chunk_tuple_list = self.hooks["modify_chunk_tuple_list"].__call__(chunk_tuple_list)

        self.total_chunks = len(chunk_tuple_list)

        try:
            os.makedirs("chunks")
        except FileExistsError:
            pass

        self.progress_bar = IncrementalBar("Downloading", max=self.total_chunks)
        #self.init_tracker()
        decrypter_provider = DecrypterProvider(self.__network__, self.m3u8)
        for chunk_number, chunk_tuple in enumerate(chunk_tuple_list):
            # We need the chunk number here to name the files. Note that this is
            # different from the chunk number that is inside the tuple.
            file_name = f"chunks\/{self.file_name}-{chunk_number}.chunk.ts"
            ChunkDownloader(
                self.__network__,
                chunk_tuple[1], # The segment data
                file_name,
                chunk_tuple[0], # The chunk number needed for decryption.
                decrypter_provider
                ).download()
            self.progress_bar.next()
            self.progress_tracker.update_chunks_done(chunk_number)
            if self.hooks.get("on_progress", None) is not None:
                self.hooks["on_progress"].__call__(chunk_number + 1, self.total_chunks)

        self.progress_bar.finish()

    def merge(self):
        """Merges the downloaded chunks into a single file.
        """
        if self.use_ffmpeg:
            FFmpegMerger(self.file_name, self.total_chunks).merge()
        else:
            ChunkMerger(self.file_name, self.total_chunks).merge()

    def remove_chunks(self):
        """Deletes the downloaded chunks.
        """
        ChunkRemover(self.file_name, self.total_chunks).remove()


class ChunkDownloader(object):
    """
    The object that actually downloads a single chunk.
    """
    def __init__(self, network, segment, file_name, chunk_number, decrypt_provider: DecrypterProvider):
        self.__network = network
        self.segment = segment
        self.file_name = file_name
        self.chunk_number = chunk_number,
        self.decrypter_provider = decrypt_provider

    def download(self):
        """Starts downloading the chunk.
        """
        with open(self.file_name, "wb") as videofile:
            res = self.__network.get(self.segment["uri"])
            chunk = res.content
            key_dict = self.segment.get("key", None)
            #This is done to check if the chunk in question is encrypted. 
            
            if key_dict is not None:
                #If the chunk is encrypted it will have a key dict.
                decrypted_chunk = self.decrypt_chunk(chunk)
                videofile.write(decrypted_chunk)
            else:
                videofile.write(chunk)
    
    def decrypt_chunk(self, chunk):
        decryter = self.decrypter_provider.get_decrypter(self.chunk_number)
        return decryter.decrypt(chunk)


class MultiThreadDownloader(object):
    """
    Facilitates downloading an episode from aniwatch.me using multiple threads.
    """
    def __init__(
        self,
        network,
        m3u8,
        file_name: str,
        id: int,
        max_threads: int = None,
        use_ffmpeg: bool = True,
        hooks = {},
        delete_chunks: bool = True,
    ):
        self.__network = network
        self.m3u8 = m3u8
        self.file_name = file_name
        self.use_ffmpeg = use_ffmpeg
        self.max_threads = max_threads
        self.delete_chunks = delete_chunks
        self.hooks = hooks
        self.progress_tracker = ProgressTracker(episode_id)
        self.__lock = Lock()
      
        try:
            os.makedirs("chunks")
        except FileExistsError:
            pass

    def init_tracker(self):
        self.progress_tracker.init_tracker(
            {
                "headers": None,
                "cookies": None,
                "segments": self.m3u8.data["segments"],
                "file_name": self.file_name,
                "total_chunks": self.total_chunks,
            }
        )


    def assign_segments(self, segment):

        ChunkDownloader(
            segment.network,
            segment.segment,
            segment.file_name,
            segment.chunk_number,
            segment.decrypter_provider
        ).download()
        with self.__lock:
            self.progress_tracker.update_chunks_done(segment.chunk_number)
            self.progress_bar.next()

    def download(self):
        """Runs the downloader and starts downloading the video file.
        """

        decrypter_provider = DecrypterProvider(self.__network, self.m3u8)
        chunk_tuple_list = []
        # Will hold a list of tuples of the form (chunk_number, chunk).
        # The chunk_number in this list will start from 0.
        for chunk_number, chunk in enumerate(self.m3u8.data["segments"]):
            chunk_tuple_list.append((chunk_number, chunk))

        if self.hooks.get("modify_chunk_tuple_list", None) is not None:
            chunk_tuple_list = self.hooks["modify_chunk_tuple_list"].__call__(chunk_tuple_list)

        self.total_chunks = len(chunk_tuple_list)
        self.progress_bar = IncrementalBar("Downloading", max=self.total_chunks)
        #self.init_tracker()

        segment_wrapper_list = []

        for chunk_number, chunk in enumerate(chunk_tuple_list):
            file_name = f"chunks\/{self.file_name}-{chunk_number}.chunk.ts"
            segment_wrapper = _SegmentWrapper(
                self.__network,
                chunk[1], # Segment data.
                file_name,
                chunk[0], # The chunk number needed for decryption.
                decrypter_provider
            )
            segment_wrapper_list.append(segment_wrapper)

        if self.max_threads == None:
            # If the value for max threads is not provided, then it is set to 
            # the total number of chunks that are to be downloaded.
            self.max_threads = self.total_chunks

        self.executor = ThreadPoolExecutor(max_workers = self.max_threads)
        
        with self.executor as exe:
            futures = exe.map(self.assign_segments, segment_wrapper_list)
            for future in futures: 
                # This loop servers to run the generator.
                pass
        self.progress_bar.finish()

    def merge(self):
        """Merges the downloaded chunks into a single file.
        """
        if self.use_ffmpeg:
            FFmpegMerger(self.file_name, self.total_chunks).merge()
        else:
            ChunkMerger(self.file_name, self.total_chunks).merge()

    def remove_chunks(self):
        """Deletes the downloaded chunks.
        """
        ChunkRemover(self.file_name, self.total_chunks).remove()

class _SegmentWrapper(object):
    # As the name suggests, this is only wrapper class introduced with a hope that it 
    # will lead to more readable code.
    def __init__(self, network, segment, file_name, chunk_number, decrypter_provider):
        self.network = network
        self.segment = segment
        self.file_name = file_name
        self.chunk_number = chunk_number
        self.decrypter_provider = decrypter_provider
