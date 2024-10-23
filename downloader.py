import os
import queue
import random
import subprocess
import threading
import time


class Downloader:
    def __init__(self, database):
        self.queue_size = 3
        self.db = database
        self.queue = queue.Queue(self.queue_size)
        self.photos_queue = queue.Queue()

    def shuffle(self, clear=True):
        # empty the queue
        if clear:
            while not self.queue.empty():
                self.queue.get()

            while not self.photos_queue.empty():
                self.photos_queue.get()

        ids = self.db.get_ids()
        random.shuffle(ids)

        for id in ids:
            self.photos_queue.put(id)

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
            print("TASK ", ids, "RUNNING")

            index = self.photos_queue.get()
            info = self.db.get_info_from_id(index)

            if info is None:
                continue

            remote, folder, file, hashed = info

            file_ext = os.path.splitext(file.lower())[-1]
            cache_folder = "cache/" + folder + "/"

            print("TASK", ids, "Downloading", folder, file)

            if os.path.exists(cache_folder + file) or os.path.exists(cache_folder + file + ".jpg"):
                print("TASK", ids, "already downloaded", folder, file)
                self.queue.put(index)
                continue

            if file_ext not in [".jpg", ".jpeg", ".png", ".heic"]:
                print("TASK", ids, "skipping videos", file)
                continue

            # create directory folder
            os.makedirs(cache_folder, exist_ok=True)

            result = subprocess.run(['rclone', "copy", remote + "album/" + folder + "/" + file, cache_folder],
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
