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
        self.photos = []

    def shuffle(self):
        # empty the queue
        while not self.queue.empty():
            self.queue.get()

        self.photos = self.db.get_ids()
        random.shuffle(self.photos)

    def start(self):

        self.shuffle()

        ids = self.db.get_recent_ids()
        for id in ids[:self.queue_size]:
            self.queue.put(id)

        # start the 3 task
        for i in range(5):
            t = threading.Thread(target=self.task, args=(i,))
            t.start()

    def get(self, block=True):
        if not block and self.queue.empty():
            return None
        return self.queue.get()



    def task(self, ids):
        while True:
            print("TASK ", ids, "RUNNING")
            time.sleep(1)

            if len(self.photos) == 0:
                continue

            index = self.photos.pop(0)
            remote, folder, file, hash = self.db.get_name_from_id(index)

            if file == "":
                continue

            file_ext = os.path.splitext(file.lower())[-1]
            cache_folder = "cache/" + folder + "/"

            print("Downloading", folder, file)

            if os.path.exists(cache_folder + file) or os.path.exists(cache_folder + file + ".jpg"):
                print("Already downloaded", folder, file)
                self.queue.put(index)
                continue

            if file_ext not in [".jpg", ".jpeg", ".png", ".heic"]:
                print("Skipping videos", file)
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
