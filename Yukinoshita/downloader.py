import aiohttp
import asyncio
import m3u8
from Crypto.Cipher import AES
import os
from multiprocessing import connection, Process, Pipe
import subprocess

SEGMENT_DIR = "Segments"
SEGMENT_EXTENSION = ".segment.ts"
OUTPUT_EXTENSION = ".mp4"


def _merge_segments(output_file_name):
    # Run the command to merge the downloaded files.
    subprocess.run(
        f"ffmpeg -f concat -safe 0 -i Segments{os.path.sep}{output_file_name}-concat_info.txt -c copy {output_file_name}{OUTPUT_EXTENSION}"
        )

def _decrypt_worker(pipe_output: connection.PipeConnection):
    while True:
        pipe_message = pipe_output.recv()
        
        # Break if a None object is encountered as this means that 
        # no more segments will be added to the pipe,
        if pipe_message is None:
            break

        segment, key, file_name = pipe_message
        if key != b"":
            decrypted_segment = AES.new(key, AES.MODE_CBC).decrypt(segment)
        else:
            decrypted_segment = segment
        with open(file_name, "wb+") as file:
            file.write(decrypted_segment)
            print(f"Written: {file_name}")

def _write_concat_info(file_name, segment_count):
    # Write the concat info needed by ffmpeg to a file.
    with open(os.path.join(SEGMENT_DIR, f"{file_name}-concat_info.txt"), "w+") as file:
        for segment_number in range(segment_count):
            f = "file "  + SEGMENT_DIR + '\\' + os.path.sep + f"{file_name}-{segment_number}{SEGMENT_EXTENSION}\n"
            file.write(f)
        

async def _download_worker(download_queue: asyncio.Queue, decrypt_pipe_input: connection.PipeConnection, client: aiohttp.ClientSession):
    while True:
        segment_data = await download_queue.get()
        file_name, segment = segment_data
        resp: aiohttp.ClientResponse = await client.get(segment.uri)
        resp_data: bytes = await resp.read()

        if segment.key is not None and segment.key !='':
            key_resp = await client.get(segment.key.uri)
            key = await key_resp.read()
        else:
            key = b""

        decrypt_pipe_input.send((
            resp_data, 
            key,
            file_name
        ))
        download_queue.task_done()


class Downloader(object):
    def __init__(self, m3u8_str: str, output_file_name: str, max_workers: int = 3) -> None:
        self._m3u8: m3u8.M3U8 = m3u8.M3U8(m3u8_str)
        self._max_workers = max_workers
        self._output_file_name = output_file_name

    async def run(self):
        # The download queue that will be used by download workers
        download_queue: asyncio.Queue = asyncio.Queue()

        # Pipe that will be used to the download workers to send the downloaded
        # data to the decrypt process for decryption and for writing to the disk.
        decrypt_pipe_output, decrypt_pipe_input = Pipe()
        client = aiohttp.ClientSession()
        
        # Check if the m3u8 file passed in has multiple streams, if this is the 
        # case then select the stream with the highest "bandwidth" specified.
        if len(self._m3u8.playlists):
            stream_uri = min(*self._m3u8.playlists, key=lambda p: p.stream_info.bandwidth).uri
            resp = await client.get(stream_uri)
            stream = m3u8.M3U8(await resp.text()) 
        else:
            stream = self._m3u8
        
        # Make sure the the SEGMENT_DIR exists.
        try:
            os.makedirs(SEGMENT_DIR)
        except FileExistsError:
            pass

        with open(os.path.join(SEGMENT_DIR, "index.yk"), "w+") as file:
            file.write("test")
        
        # Start the process that will decrypt and write the files to disk.
        decrypt_process = Process(target=_decrypt_worker, args=(decrypt_pipe_output,), daemon=True)
        decrypt_process.start()

        # Populate the download queue.
        for segment_number, segment in enumerate(stream.segments):
            await download_queue.put((
                os.path.join(SEGMENT_DIR,f"{self._output_file_name}-{segment_number}{SEGMENT_EXTENSION}"),
                segment
                ))

        # Start the workers but wrapping the coroutines into tasks.
        workers = [
            asyncio.create_task(_download_worker(download_queue, decrypt_pipe_input, client))
            for _ in range(self._max_workers)
        ]
        
        # Wait for the download workers to finish.
        await download_queue.join()

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
        _write_concat_info(self._output_file_name, len(stream.segments))
        _merge_segments(self._output_file_name)


    @classmethod
    async def from_url(cls, url, output_file_name, max_workers=5):
        client = aiohttp.ClientSession()
        resp = await client.get(url)
        resp_text = await resp.text()
        await client.close()
        return cls(resp_text, output_file_name, max_workers)

    @classmethod
    async def from_file(cls, file_path, output_file_name, max_workers=5):
        with open(file_path, "r") as file:
            m3u8 = file.read()
        return cls(m3u8, output_file_name, max_workers)

async def main():
    d = await Downloader.from_url("https://vengeance.animex.vip/GYJQV73V6/episodes/1/master.m3u8", "demo", 20)
    await d.run()
if __name__ == "__main__":
    asyncio.run(main())