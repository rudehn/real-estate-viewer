import httpx

from county import sources

INDEX = (
    '<a href=data\\Cama\\Cama_Files_20260630.zip>Cama_Files_20260630.zip</a>'
    '<a href=data\\Cama\\Cama_Files_20260831.zip>Cama_Files_20260831.zip</a>'
    '<a href=data\\Cama\\Cama_Files_20260731.zip>Cama_Files_20260731.zip</a>'
)


def client_for(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_list_files_sorted_and_deduplicated():
    def handler(request):
        assert request.url.params["dtype"] == "CC"
        return httpx.Response(200, text=INDEX + INDEX)

    async with client_for(handler) as client:
        files = await sources.list_files("cama", client)
    assert files == [
        "Cama_Files_20260630.zip", "Cama_Files_20260731.zip", "Cama_Files_20260831.zip"
    ]


async def test_latest_file():
    async with client_for(lambda r: httpx.Response(200, text=INDEX)) as client:
        assert await sources.latest_file("cama", client) == "Cama_Files_20260831.zip"


async def test_latest_file_when_index_is_empty():
    async with client_for(lambda r: httpx.Response(200, text="<html></html>")) as client:
        assert await sources.latest_file("taxroll", client) is None


async def test_download_streams_to_dataset_folder(tmp_path):
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, content=b"zipbytes")

    async with client_for(handler) as client:
        path = await sources.download("taxroll", "TAXROLL_20260923.zip", tmp_path, client)
        again = await sources.download("taxroll", "TAXROLL_20260923.zip", tmp_path, client)
    assert path == tmp_path / "Taxroll" / "TAXROLL_20260923.zip"
    assert path.read_bytes() == b"zipbytes"
    assert again == path
    assert seen == [
        "https://go.mcohio.org/applications/treasurer/search/data/Taxroll/TAXROLL_20260923.zip"
    ]


async def test_failed_download_leaves_no_partial_file(tmp_path):
    async with client_for(lambda r: httpx.Response(500)) as client:
        try:
            await sources.download("cama", "Cama_Files_20260831.zip", tmp_path, client)
        except httpx.HTTPStatusError:
            pass
    assert not (tmp_path / "Cama" / "Cama_Files_20260831.zip").exists()
    assert list((tmp_path / "Cama").glob("*")) == []
