import asyncio
import random


async def produce(queue, n):
    for x in range(n):
        # produce an item
        print('producing {}/{}'.format(x, n))
        # simulate i/o operation using sleep
        await asyncio.sleep(random.random())
        item = str(x)
        # put the item in the queue
        await queue.put(item)


async def consume(queue):
    while True:
        # wait for an item from the producer
        item = await queue.get()

        # process the item
        print('consuming {}...'.format(item))
        # simulate i/o operation using sleep
        await asyncio.sleep(5)

        # Notify the queue that the item has been processed
        queue.task_done()


async def run(n):
    queue = asyncio.Queue()
    # schedule the consumer
    consumers = [asyncio.create_task(consume(queue)) for x in range(5)]
    # run the producer and wait for completion
    await produce(queue, n)
    # wait until the consumer has processed all items
    await queue.join()
    # the consumer is still awaiting for an item, cancel it
    for consumer in consumers:
        consumer.cancel()


loop = asyncio.get_event_loop()
loop.run_until_complete(run(10))
loop.close()

# import asyncio
# from asyncio import queues

# async def producers(queue):
#     for x in range(10):
#         item = str(x)
#         await queue.put("1")

# async def consume(queue):
#     while True:
#         item =  await queue.get()
#         print(item)
#         await asyncio.sleep(2)
#         queue.task_done()

# async def run():
#     queue = asyncio.Queue()
#     consumer = asyncio.create_task(consume(queue))
#     await producers(queue)
#     await queue.join()
#     consumer.cancel()

# asyncio.run(run())