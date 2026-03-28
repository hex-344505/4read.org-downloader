import os
import re
import sys
import time
import requests

from bs4 import BeautifulSoup

from urllib.parse import (
    urljoin,
    urlsplit,
    urlunsplit,
    quote,
    unquote
)

from concurrent.futures import ThreadPoolExecutor


BASE_PLAYLIST_URL = "https://4read.org/m3u/"

THREADS = 3
RETRIES = 5
CHUNK = 8192


def normalize_url(url):

    url = url.replace("\\", "/")

    parts = urlsplit(url)

    path = unquote(parts.path)

    encoded_path = quote(path, safe="/")

    return urlunsplit((
        parts.scheme,
        parts.netloc,
        encoded_path,
        parts.query,
        parts.fragment
    ))


def safe_filename(url, index):

    name = os.path.basename(unquote(urlsplit(url).path))

    if not name:
        name = f"{index:04d}.mp3"

    return f"{index:04d}_{name}"


def parse_book_page(url):

    headers = {
        "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    author = None
    title = None

    for img in soup.find_all("img"):

        alt = img.get("alt")

        if alt and " - " in alt:

            author, title = alt.split(" - ", 1)

            author = author.strip()
            title = title.strip()

            break

    playlist = None

    scripts = soup.find_all("script")

    for s in scripts:

        if not s.string:
            continue

        match = re.search(r'file:"([^"]+\.m3u)"', s.string)

        if match:

            file_value = match.group(1)

            file_value = file_value.replace("{v1}", "")

            playlist = BASE_PLAYLIST_URL + file_value

            break

    return author, title, playlist


def parse_m3u(playlist_url):

    r = requests.get(playlist_url, timeout=30)
    r.raise_for_status()

    base = playlist_url
    urls = []

    for line in r.text.splitlines():

        line = line.strip()

        if not line:
            continue

        if line.startswith("#"):
            continue

        urls.append(urljoin(base, line))

    return urls


def download_file(task):

    url, folder, index = task

    url = normalize_url(url)

    filename = safe_filename(url, index)

    filepath = os.path.join(folder, filename)

    for attempt in range(RETRIES):

        try:

            headers = {}

            downloaded = 0

            if os.path.exists(filepath):

                downloaded = os.path.getsize(filepath)

                headers["Range"] = f"bytes={downloaded}-"

            r = requests.get(url, stream=True, timeout=60, headers=headers)

            r.raise_for_status()

            mode = "ab" if downloaded else "wb"

            with open(filepath, mode) as f:

                for chunk in r.iter_content(CHUNK):

                    if chunk:
                        f.write(chunk)

            print(f"Downloaded: {filename}")

            return

        except Exception as e:

            if attempt < RETRIES - 1:

                print(f"Retry: {filename}")

                time.sleep(2)

            else:

                print(f"FAILED: {filename} -> {e}")


def main():

    if len(sys.argv) < 2:

        print("Usage:")
        print("python book_downloader.py BOOK_URL")

        return


    book_url = sys.argv[1]

    print("Reading book page...")

    author, title, playlist = parse_book_page(book_url)

    if not playlist:

        print("Playlist not found")
        return


    if author and title:
        folder = f"{author} - {title}"
    else:
        folder = "audiobook"

    print("Book:", folder)
    print("Playlist:", playlist)


    os.makedirs(folder, exist_ok=True)


    print("Reading playlist...")

    files = parse_m3u(playlist)

    print(f"Files found: {len(files)}")


    tasks = [(url, folder, i + 1) for i, url in enumerate(files)]


    print("Starting download...\n")


    with ThreadPoolExecutor(max_workers=THREADS) as executor:

        executor.map(download_file, tasks)


    print("\nDownload finished")


if __name__ == "__main__":
    main()
