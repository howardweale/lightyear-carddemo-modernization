"""Bounded nonblocking public stderr capture for this NO-KEY CI observer only."""
import os

LIMIT = 4096


class BoundedStderr:
    def __init__(self):
        self.read_fd, self.write_fd = os.pipe()
        self.data = bytearray()
        self.eof = self.overflow = self.read_error = False
        try:
            os.set_blocking(self.read_fd, False)
        except BaseException:
            self.close()
            raise

    def close_writer(self):
        if self.write_fd is not None:
            os.close(self.write_fd)
            self.write_fd = None

    def drain(self):
        # At most LIMIT+1 total bytes are read, including an overflow sentinel.
        # A descendant retaining the writer never makes this method wait.
        while not (self.eof or self.overflow or self.read_error):
            try:
                part = os.read(self.read_fd, min(1024, LIMIT + 1 - len(self.data)))
            except BlockingIOError:
                return
            except OSError:
                self.read_error = True
                return
            if not part:
                self.eof = True
                return
            remaining = LIMIT - len(self.data)
            self.data.extend(part[:remaining])
            if len(part) > remaining:
                self.overflow = True

    def check(self, *, final=False):
        self.drain()
        if self.overflow or self.read_error or (final and not self.eof):
            raise ValueError("bounded stderr overflow, read failure or incomplete EOF")

    def fields(self):
        # Consumers print these only through json.dumps; never raw terminal bytes.
        return dict(stderr_hex=self.data.hex(),
                    stderr_text=self.data.decode("utf-8", errors="backslashreplace"),
                    stderr_retained_bytes=len(self.data), stderr_limit=LIMIT,
                    stderr_eof=self.eof, stderr_overflow=self.overflow,
                    stderr_read_error=self.read_error)

    def close(self):
        self.close_writer()
        if self.read_fd is not None:
            os.close(self.read_fd)
            self.read_fd = None
