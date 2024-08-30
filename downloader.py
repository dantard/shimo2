import os
import queue
import random
import subprocess
import threading
import time


class Downloader:
    def __init__(self, database):
        self.db = database
        # Queue max size is 3
        self.queue = queue.Queue(3)
        self.photos = []

    def start(self):
        self.photos = self.db.get_ids()
        random.shuffle(self.photos)

        # start the 3 task
        for i in range(3):
            t = threading.Thread(target=self.task)
            t.start()

    def get(self, block=True):
        if not block and self.queue.empty():
            return None
        return self.queue.get()

    def task(self):
        while True:
            if len(self.photos) > 0:
                index = self.photos.pop(0)
                folder, file = self.db.get_name_from_id(index)
                # create directory folder
                os.makedirs("cache/" + folder, exist_ok=True)

                result = subprocess.run(['rclone', "copy", "gphoto:album/" + folder + "/" + file, "cache/" + folder + "/"],
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE,
                                        text=True)
                print(result)

                if result.returncode == 0:
                    print("putting")
                    self.queue.put(index)
                    print("putted")
            time.sleep(1)
