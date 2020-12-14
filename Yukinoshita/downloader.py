import aiofile
import aiohttp
import asyncio
import m3u8
from Crypto.Cipher import AES
import typing
import os

async def _worker(queue: asyncio.Queue, client: aiohttp.ClientSession):
    while True:
        try:
            segment_data = await queue.get()
            file_name: str = segment_data[0]
            segment: typing.List[m3u8.Segment] = segment_data[1]
            resp: aiohttp.ClientResponse = await client.get(segment.uri)
            resp_data: bytes = await resp.read()

            if segment.key is not None and segment.key !='':
                key_resp = await client.get(segment.key.uri)
                key = await key_resp.read()
                print("Decrypt key received.")
                data_to_write = AES.new(key, AES.MODE_CBC).decrypt(resp_data)
                print("Decrypted")
            else:
                data_to_write = resp_data
            async with aiofile.async_open(file_name, "wb+") as file:
                await file.write(data_to_write)
            print("Written")
            queue.task_done()
        except: 
            print("Quitting")

class Downloader(object):
    def __init__(self, m3u8_str: str, output_file_name: str, max_workers: int = 3) -> None:
        self._m3u8: m3u8.M3U8 = m3u8.M3U8(m3u8_str)
        self._max_workers = max_workers
        self._output_file_name = output_file_name

    async def run(self):
        queue = asyncio.Queue()
        client = aiohttp.ClientSession()
        
        if len(self._m3u8.playlists):
            stream_uri = max(*self._m3u8.playlists, key=lambda p: p.stream_info.bandwidth).uri
            resp = await client.get(stream_uri)
            stream = m3u8.M3U8(await resp.text()) 
        else:
            stream = self._m3u8
        
        try:
            os.makedirs("segments")
        except FileExistsError:
            pass

        async with aiofile.async_open(os.path.join("segments", "index.yk"), "w+") as file:
            await file.write("test")
        
        for segment_number, segment in enumerate(stream.segments):
            await queue.put((
                os.path.join("segments",f"{self._output_file_name}-{segment_number}.chunk"),
                segment
                ))

        workers = [
            asyncio.create_task(_worker(queue, client))
            for _ in range(self._max_workers)
        ]
        
        await queue.join()

        for worker in workers:
            worker.cancel()
        
        await client.close()

    @classmethod
    async def from_url(cls, url, output_file_name, max_workers=5):
        client = aiohttp.ClientSession()
        resp = await client.get(url)
        resp_text = await resp.text()
        await client.close()
        return cls(resp_text, output_file_name, max_workers)

async def main():
    d = await Downloader.from_url("https://vengeance.animex.vip/GYJQV73V6/episodes/2/master.m3u8", "demo", 20)
    await d.run()
asyncio.run(main())