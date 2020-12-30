import aiohttp
import asyncio
import m3u8
from Crypto.Cipher import AES
import os
from multiprocessing import Semaphore, connection, Process, Pipe
import subprocess
import logging

# logging.basicConfig(level=logging.CRITICAL)

SEGMENT_DIR = "Segments"
SEGMENT_EXTENSION = ".segment.ts"
RESUME_EXTENSION = ".resumeinfo.yuk"
OUTPUT_EXTENSION = ".mp4"


def _parse_resume_info(raw_file_data):
    lines = raw_file_data.split("\n")
    lines = filter(
        lambda line: line.startswith("SEGMENT"),
        lines
    )
    return tuple(
        int(line.split(" ")[1])
        for line in lines
    )


def _write_resume_info(file_name, segment_number):
    with open(file_name, "a") as file:
        file.write(f"SEGMENT {segment_number}\n")


def _merge_segments(output_file_name):
    # Run the command to merge the downloaded files.
    subprocess.run(
        f"ffmpeg -f concat -safe 0 -i Segments{os.path.sep}{output_file_name}-concat_info.txt -c copy {output_file_name}{OUTPUT_EXTENSION} -hide_banner -loglevel warning"
    )


def _decrypt_worker(
        pipe_output: connection.PipeConnection,
        resume_file_path: str,
        progress_tracker):
    logging.debug("Decrypt process started.")
    while True:
        pipe_message = pipe_output.recv()

        # Break if a None object is encountered as this means that
        # no more segments will be added to the pipe,
        if pipe_message is None:
            break

        segment, key, file_name, segment_number = pipe_message
        if key != b"":
            decrypted_segment = AES.new(key, AES.MODE_CBC).decrypt(segment)
            logging.info(f"Decrypted segment number {segment_number}.")
        else:
            decrypted_segment = segment

        with open(file_name, "wb+") as file:
            file.write(decrypted_segment)

        # Update the resume info.
        _write_resume_info(resume_file_path, segment_number)

        logging.info(f"Wrote: {file_name}")

        # Display the progress.
        progress_tracker.increment_done()
        progress_tracker.display()


def _write_concat_info(file_name, segment_count):
    # Write the concat info needed by ffmpeg to a file.
    with open(os.path.join(SEGMENT_DIR, f"{file_name}-concat_info.txt"), "w+") as file:
        for segment_number in range(segment_count):
            f = "file " + SEGMENT_DIR + '\\' + os.path.sep + \
                f"{file_name}-{segment_number}{SEGMENT_EXTENSION}\n"
            file.write(f)
    logging.info("Wrote Concat Info.")


async def _download_worker(download_queue: asyncio.Queue, decrypt_pipe_input: connection.PipeConnection, client: aiohttp.ClientSession):
    logging.debug("Started download worker.")
    while True:
        segment_data = await download_queue.get()
        file_name, segment, segment_number = segment_data
        resp: aiohttp.ClientResponse = await client.get(segment.uri)
        resp_data: bytes = await resp.read()
        logging.info(f"Fetched segment number {segment_number}.")

        if segment.key is not None and segment.key != '':
            key_resp = await client.get(segment.key.uri)
            key = await key_resp.read()
        else:
            key = b""

        decrypt_pipe_input.send((
            resp_data,
            key,
            file_name,
            segment_number
        ))
        download_queue.task_done()


class ProgressTracker(object):
    def __init__(self, total: int) -> None:
        self.total = total
        self.done = 0

    def display(self) -> None:
        print(f"{self.done}/{self.total} done.", end="\r")

    def increment_done(self) -> None:
        self.done += 1


class Downloader(object):
    def __init__(
            self,
            m3u8_str: str,
            output_file_name: str,
            resume_code=None,
            max_workers: int = 3) -> None:
        self._m3u8: m3u8.M3U8 = m3u8.M3U8(m3u8_str)
        self._max_workers = max_workers
        self._output_file_name = output_file_name.replace(" ", "-")
        self._resume_code = resume_code or self._output_file_name

    async def run(self):
        # The download queue that will be used by download workers
        download_queue: asyncio.Queue = asyncio.Queue()

        # Pipe that will be used to the download workers to send the downloaded
        # data to the decrypt process for decryption and for writing to the
        # disk.
        decrypt_pipe_output, decrypt_pipe_input = Pipe()
        client = aiohttp.ClientSession()

        # Check if the m3u8 file passed in has multiple streams, if this is the
        # case then select the stream with the highest "bandwidth" specified.
        if len(self._m3u8.playlists):
            stream_uri = max(
                *self._m3u8.playlists,
                key=lambda p: p.stream_info.bandwidth).uri
            resp = await client.get(stream_uri)
            stream = m3u8.M3U8(await resp.text())
        else:
            stream = self._m3u8
        logging.info("Selected playlist.")

        # Make sure the the SEGMENT_DIR exists.
        try:
            os.makedirs(SEGMENT_DIR)
        except FileExistsError:
            pass

        resume_file_path = os.path.join(
            SEGMENT_DIR, f"{self._resume_code}{RESUME_EXTENSION}")
        if os.path.isfile(resume_file_path):
            with open(resume_file_path) as file:
                resume_info = _parse_resume_info(file.read())
            logging.info(f"Resume data found for {self._resume_code}.")
        else:
            with open(resume_file_path, "w+") as file:
                pass
            resume_info = []
            logging.info(f"No resume data found for {self._resume_code}")

        assert len(stream.segments) != 0

        segment_list = tuple(
            filter(
                lambda seg: seg[0] not in resume_info,
                enumerate(
                    stream.segments)))

        progress_tracker = ProgressTracker(len(segment_list))

        # Start the process that will decrypt and write the files to disk.
        decrypt_process = Process(
            target=_decrypt_worker,
            args=(
                decrypt_pipe_output,
                resume_file_path,
                progress_tracker),
            daemon=True)
        decrypt_process.start()
        logging.debug("Running decrypt process.")

        # Populate the download queue.
        for segment_number, segment in segment_list:
            await download_queue.put((
                os.path.join(SEGMENT_DIR, f"{self._resume_code}-{segment_number}{SEGMENT_EXTENSION}"),
                segment,
                segment_number
            ))

        # Start the workers but wrapping the coroutines into tasks.
        logging.info(f"Starting {self._max_workers} download workers.")
        workers = [
            asyncio.create_task(
                _download_worker(
                    download_queue,
                    decrypt_pipe_input,
                    client)) for _ in range(
                self._max_workers)]

        # Wait for the download workers to finish.
        await download_queue.join()
        logging.info("Downloading complete.")

        # After all the tasks in the download queue are finished,
        # put a None into the decrypt pip to stop the decrypt process.
        decrypt_pipe_input.send(None)
        decrypt_pipe_input.close()

        # Cancel all download workers.
        for worker in workers:
            worker.cancel()

        await client.close()  # CLose the http session.

        # Wait for the process to finish.
        decrypt_process.join()

        # Write the concat info and invoke ffmpeg to concatinate the files.
        _write_concat_info(self._resume_code, len(stream.segments))
        _merge_segments(self._output_file_name)

    @classmethod
    async def from_url(cls, url: str, output_file_name: str, resume_code=None, max_workers: int = 3):
        client = aiohttp.ClientSession()
        resp = await client.get(url)
        resp_text = await resp.text()
        await client.close()
        return cls(resp_text, output_file_name, resume_code, max_workers)

    @classmethod
    async def from_file(cls, file_path: str, output_file_name: str, resume_code=None, max_workers: int = 3):
        with open(file_path, "r") as file:
            m3u8 = file.read()
        return cls(m3u8, output_file_name, resume_code, max_workers)
