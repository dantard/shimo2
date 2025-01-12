import os
import queue
import random
import subprocess
import sys
import threading
import time


class Downloader:
    def __init__(self, database):
        self.loop_mode = 1
        self.directory = "shared-album"
        self.directory = "album"
        self.queue_size = 3
        self.db = database
        self.queue = queue.Queue(self.queue_size)
        self.photos_queue = queue.Queue()

    def set_loop_mode(self, mode):
        self.loop_mode = mode
        self.shuffle(True)

    def clear_queue(self):
        while not self.queue.empty():
            self.queue.get()

        while not self.photos_queue.empty():
            self.photos_queue.get()

    def shuffle0(self, clear=True):
        if clear:
            self.clear_queue()
        ids = self.db.get_ids()
        random.shuffle(ids)
        for id in ids:
            self.photos_queue.put(id)

    def shuffle(self, clear=True):
        if self.loop_mode == 0:
            self.shuffle0(clear)
        elif self.loop_mode == 1:
            self.shuffle1(clear)

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
        for i in range(5):
            threading.Thread(target=self.download, args=(i,)).start()

    def get(self, block=True):
        if not block and self.queue.empty():
            return None
        return self.queue.get()

    def download(self, ids):
        while True:
            # print("TASK ", ids, "RUNNING")

            index = self.photos_queue.get()
            info = self.db.get_info_from_id(index)

            print("got id", index, info)

            if info is None:
                continue

            remote, folder, file, hashed = info

            file_ext = os.path.splitext(file.lower())[-1]
            cache_folder = "cache/" + folder + "/"

            # print("TASK", ids, "Downloading", folder, file)

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
                print(result.stderr)
                continue

            if file_ext in [".jpg", ".jpeg", ".png"]:
                # Resize
                self.queue.put(index)

            elif file_ext in [".heic"]:
                result = subprocess.run(["convert", "cache/" + folder + "/" + file, cache_folder + file + ".jpg"],
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE,
                                        text=True)

                if result.returncode != 0:
                    print(result.stderr)
                    continue

                os.remove(cache_folder + file)
                # Resize
                self.queue.put(index)
