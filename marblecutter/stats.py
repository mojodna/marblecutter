import time


class Timer(object):
    def __enter__(self):
        self.start = time.time()
        return self

    def __exit__(self, ty, val, tb):
        self.end = time.time()
        self.elapsed = self.end - self.start
