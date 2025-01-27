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
        self.loop_mode = 1
        self.directory = "shared-album"
        self.directory = "album"
        self.queue_size = 3
        self.db = database
        self.queue = queue.Queue(self.queue_size)
        self.photos_queue = queue.Queue()
        self.drop = [False] * Downloader.MAX_THREADS

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

    def play(self,remote, title):
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

    def download(self, _id):
        while True:
            # print("TASK ", ids, "RUNNING")

            index = self.photos_queue.get()
            info = self.db.get_info_from_id(index)

            if info is None:
                continue

            remote, folder, file, hashed = info

            if remote.startswith("file:"):
                self.queue.put(index)
                continue

            file_ext = os.path.splitext(file.lower())[-1]
            cache_folder = "cache/" + folder + "/"

            if os.path.exists(cache_folder + file) or os.path.exists(cache_folder + file + ".jpg"):
                # print("TASK", ids, "already downloaded", folder, file)
                self.queue.put(index)
                continue

            if file_ext not in [".jpg", ".jpeg", ".png", ".heic"]:
                # print("TASK", ids, "skipping videos", file)
                continue

            # create directory folder
            os.makedirs(cache_folder, exist_ok=True)

            result = subprocess.run(
                ['rclone', "copy", remote + "/" + folder + "/" + file, cache_folder],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True)

            if result.returncode != 0:
                continue

            if file_ext in [".jpg", ".jpeg", ".png"]:
                filename = cache_folder + file

            elif file_ext in [".heic"]:
                result = subprocess.run(["convert", "cache/" + folder + "/" + file, cache_folder + file + ".jpg"],
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE,
                                        text=True)
                filename = cache_folder + file + ".jpg"
                if result.returncode != 0:
                    print(result.stderr)
                    continue

                os.remove(cache_folder + file)
            else:
                continue

            try:
                # resize the image to reduce workload
                p = Pilmage.open(filename)
                if p.width > p.height:
                    if p.height > 1080:
                        # landscape, resize in a way that the height is 1080 respecting the aspect ratio
                        p = p.resize((int(p.width * 1080 / p.height), 1080))
                else:
                    if p.width > 1920:
                        # portrait, resize in a way that the width is 1920 respecting the aspect ratio
                        p = p.resize((1920, int(p.height * 1920 / p.width)))
                # save the resized image
                p.save(filename)
                p.close()
            except:
                pass

            if self.drop[_id]:
                self.drop[_id] = False
            else:
                self.queue.put(index)



