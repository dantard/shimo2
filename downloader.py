import os
import queue
import random
import struct
import subprocess
import sys
import threading
import time
from PIL import Image as Pilmage


class Downloader:
    MAX_THREADS = 5

    def __init__(self, database):
        self.cache_size = 0
        self.loop_mode = 1
        self.directory = "shared-album"
        self.directory = "album"
        self.queue_size = 3
        self.db = database
        self.queue = queue.Queue(self.queue_size)
        self.photos_queue = queue.Queue()
        self.drop = [False] * Downloader.MAX_THREADS

    def get_cache_size(self):
        return self.cache_size

    def set_loop_mode(self, mode):
        self.loop_mode = mode
        self.shuffle(True)

    def clear_queue(self):

        for i in range(Downloader.MAX_THREADS):
            self.drop[i] = True

        while not self.queue.empty():
            self.queue.get()

        while not self.photos_queue.empty():
            self.photos_queue.get()

    def shuffle0(self, clear=True):
        if clear:
            self.clear_queue()
        ids = self.db.get_ids_by_seen()
        random.shuffle(ids)
        for id in ids:
            self.photos_queue.put(id)

        print("shuffle0", ids)

    def shuffle2(self, clear=True):
        if clear:
            self.clear_queue()
        remotes = self.db.get_remotes()
        for remote in remotes:
            albums = self.db.get_albums(remote)
            random.shuffle(albums)
            for _, title, active in albums:
                if active:
                    photo_ids = self.db.get_ids_by_album(remote, title)
                    for id in photo_ids:
                        self.photos_queue.put(id)

    def play(self, remote, title):
        ids = self.db.get_ids_by_album(remote, title)

        print("play", remote, title, ids)
        self.clear_queue()
        for id in ids:
            self.photos_queue.put(id)

    def shuffle(self, clear=True):
        if self.loop_mode == 0:
            self.shuffle0(clear)
        elif self.loop_mode == 1:
            self.shuffle1(clear)
        elif self.loop_mode == 2:
            self.shuffle2(clear)

    def shuffle1(self, clear=True):
        if clear:
            self.clear_queue()

        count, ids = 0, []
        remotes = self.db.get_remotes()

        class Container:
            def __init__(self, ids):
                self.ids = ids
                self.count = 0

            def next(self):
                if len(self.ids) == 0:
                    return None
                self.count = 0 if self.count >= len(self.ids) else self.count
                my_id = self.ids[self.count]
                self.count += 1
                return my_id

        for remote in remotes:
            albums = self.db.get_albums(remote)
            for _, title, active in albums:
                if active:
                    print("albums", title)
                    photo_ids = self.db.get_ids_by_album(remote, title)
                    random.shuffle(photo_ids)
                    ids.append(Container(photo_ids))
                    count += len(photo_ids)

        random.shuffle(ids)

        shorter_list_len = min([len(x.ids) for x in ids])
        shorter_list_len = max([shorter_list_len, 100])

        for i in range(shorter_list_len):
            for album in ids:
                next_id = album.next()
                if next_id is not None:
                    self.photos_queue.put(next_id)

    def start(self):
        # start the 5 producer tasks
        for i in range(Downloader.MAX_THREADS):
            threading.Thread(target=self.download, args=(i,)).start()

    def get(self, block=True):
        if not block and self.queue.empty():
            return None
        return self.queue.get()

    def is_empty(self):
        return self.queue.empty()

    def deal_with_heif(self, filename, output):
        result = subprocess.run(["identify", "-format", '%w,%h', filename], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, check=True)
        if result.returncode != 0:
            return False

        w, h = result.stdout.split(",")
        w, h = int(w), int(h)
        if w > h:
            fmt = ["-resize", "x1080"] if h > 1080 else []
        else:
            fmt = ["-resize", "1920x"] if w > 1920 else []

        result = subprocess.run(
            ["convert"] + fmt + [filename, output],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True)
        print(["convert"] + fmt + [filename, output], result.returncode, result.stdout, result.stderr)
        return result.returncode == 0

    def download(self, _id):
        while True:

            # Get next photo index
            index = self.photos_queue.get()
            info = self.db.get_info_from_id(index)

            # if info not found, skip
            if info is None:
                continue

            remote, folder, file, hashed = info

            # if it is a local file
            if remote.startswith("file:"):
                filename = remote.replace("file:", "") + "/" + folder + "/" + file

                # if for some reason the file does not exist, skip
                if not os.path.exists(filename):
                    continue

                # if it is a heic file, convert it to jpg
                if filename.endswith(".heic"):
                    self.deal_with_heif(filename, filename + ".jpg")

                # put the index in the choose queue
                self.queue.put(index)
                continue

            # if it is a remote file
            file_ext = os.path.splitext(file.lower())[-1]
            cache_folder = "cache/" + folder + "/"

            if os.path.exists(cache_folder + file) or os.path.exists(cache_folder + file + ".jpg"):
                self.queue.put(index)
                continue

            # if it is not a jpg, jpeg, png or heic file, skip
            if file_ext not in [".jpg", ".jpeg", ".png", ".heic"]:
                continue

            # create directory folder in case it does not exist
            os.makedirs(cache_folder, exist_ok=True)

            # get the file from the remote
            result = subprocess.run(
                ['rclone', "copy", remote + "/" + folder + "/" + file, cache_folder],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True)

            # if the file was not downloaded, skip
            if result.returncode != 0:
                continue

            # if it is a heic file, convert it to jpg
            if file_ext in [".heic"]:
                filename = cache_folder + file

                if not self.deal_with_heif(filename, filename + ".jpg"):
                    os.remove(filename)
                    continue

                os.remove(filename)

            # Update the cache size
            result = subprocess.run(
                ['du', "-sm", "cache"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True)

            size, _ = result.stdout.split("\t")
            self.cache_size = int(size)

            # if I don't need to drop the photo
            # put the index in the choose queue
            if self.drop[_id]:
                self.drop[_id] = False
            else:
                self.queue.put(index)

    def run_command(self, command):
        if type(command) == str:
            command = command.split(" ")
        try:
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True)
        except Exception as e:
            pass

        return result.returncode == 0, result.stdout, result.stderr
