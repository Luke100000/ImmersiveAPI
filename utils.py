import aiofile
import aiohttp


async def fetch_file(url, target):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            assert resp.status == 200
            data = await resp.read()

        async with aiofile.async_open(target, "wb") as outfile:
            await outfile.write(data)
