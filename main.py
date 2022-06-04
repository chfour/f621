import stat, os, errno, fuse
from typing import Generator

fuse.fuse_python_api = (0, 2)

FILES = {"/test": b"Hello, world!"}

class TheFS(fuse.Fuse):
    def getattr(self, path: str) -> fuse.Stat:
        st = fuse.Stat()
        
        if path == "/":
            st.st_mode = stat.S_IFDIR | 0o755
            st.st_nlink = 2
        elif path in FILES:
            st.st_mode = stat.S_IFREG | 0o444
            st.st_nlink = 1
            st.st_size = len(FILES[path])
        else:
            print(f"getattr {path} -> ENOENT")
            return -errno.ENOENT
        
        print(f"getattr {path} -> {st.__dict__}")
        return st

    def readdir(self, path, offset) -> Generator[fuse.Direntry, None, None]:
        for f in [".", ".."] + [e[1:] for e in FILES]:
            yield fuse.Direntry(f)

def main() -> None:
    server = TheFS(dash_s_do="setsingle")
    server.parse(errex=1)
    server.main()

if __name__ == "__main__":
    main()
