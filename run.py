from multiprocessing import Process

from peering_sync_daemon import main
from peering_sync_panel import run


if __name__ == '__main__':
    p1 = Process(target=main)
    p2 = Process(target=run)

    p1.start()
    p2.start()

    p1.join()
    p2.join()