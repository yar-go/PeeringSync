import hashlib
import os.path
import shutil
import typing
from math import ceil
from functools import lru_cache

from .bitfield import BitField


class FilesManager:
    """Об'єкти цього класу надають можливість записувати певну кількість байтів за номером куску торент-файлів
    та отримувати дані торент-файлів не зважаючи на структуру завантажувальних файлів"""
    def __init__(self, full_length: int, bitfield: BitField, block_size: int, destination: str,
                 files: typing.Sequence[tuple[int, str]]):
        self._full_length = full_length
        self._bitfield = bitfield
        self._data_count_per_piece = block_size
        self._files = files
        self._destination = destination

    @property
    def destination(self):
        return self._destination

    def write_block(self, data: bytes, block_index: int) -> None:
        block_start_index = block_index * self._data_count_per_piece
        block_end_index = block_start_index + self._data_count_per_piece

        total = 0
        for file_size, file, _ in self._files:
            file_start_index = total
            file_end_index = total + file_size - 1

            if file_start_index <= block_start_index <= block_end_index <= file_end_index:  # блок всередині файлу
                self._write_data_file(file, data, block_start_index - file_start_index)
            elif block_start_index <= file_start_index <= file_end_index <= block_end_index:  # файл всередині блоку
                self._write_data_file(file,
                                      data[file_start_index - block_start_index:file_end_index - block_start_index + 1],
                                      0)
            elif file_start_index <= block_start_index <= file_end_index <= block_end_index:  # файл починається до бло
                self._write_data_file(file, data[:file_end_index - block_start_index + 1], block_start_index - file_start_index)
            elif block_start_index <= file_start_index <= block_end_index <= file_end_index:  # файл починається в серд
                self._write_data_file(file, data[file_start_index - block_start_index:], 0)
            total += file_size
        self._bitfield.set(block_index)

    # @lru_cache(1000)
    def read_piece(self, piece_index: int) -> bytes:
        res = b''
        block_start_index = piece_index * self._data_count_per_piece
        block_end_index = block_start_index + self._data_count_per_piece - 1

        total = 0
        for file_size, file, _ in self._files:
            file_start_index = total
            file_end_index = total + file_size - 1

            if file_start_index <= block_start_index <= block_end_index <= file_end_index:  # блок всередині файлу
                res += self._read_data_file(file, block_start_index - file_start_index,
                                            block_end_index - block_start_index + 1)
            elif block_start_index <= file_start_index <= file_end_index <= block_end_index:  # файл всередині блоку
                res += self._read_data_file(file, 0, file_size)
            elif file_start_index <= block_start_index <= file_end_index <= block_end_index:  # файл починається до бло
                res += self._read_data_file(file, block_start_index - file_start_index,
                                            file_end_index - block_start_index + 1)
            elif block_start_index <= file_start_index <= block_end_index <= file_end_index:  # файл починається в серд
                res += self._read_data_file(file, 0, block_end_index - file_start_index + 1)
            total += file_size
        return res

    def _write_data_file(self, filepath: str, data: bytes, start_index: int) -> int:
        paths = os.path.join(os.path.dirname(filepath))
        if paths and not os.path.exists(os.path.join(self._destination,paths)): os.makedirs(os.path.join(self._destination,paths))
        open_mode = "w+b" if not os.path.exists(os.path.join(self._destination, filepath)) else "r+b"
        with open(os.path.join(self._destination, filepath), open_mode) as f:
            f.seek(start_index)
            return f.write(data)

    def _read_data_file(self, filepath: str, start_index: int, length_block: int) -> bytes:
        with open(os.path.join(self._destination, filepath), "rb") as f:
            f.seek(start_index)
            return f.read(length_block)

    def relocate(self, seed):
        file_paths = []
        for root, dirs, files in os.walk(self._destination):
            for name in files:
                file_paths.append(os.path.join(root, name))

        local_files = dict()
        for file_path in file_paths:
            with open(file_path, "rb") as f:
                content = f.read()
                file_hash = hashlib.sha1(content).digest()
                local_files[file_hash] = file_path

        updated_files = dict()
        for f in seed.files:
            updated_files[f[2]] = os.path.join(self._destination, f[1])

        for lfh in local_files:
            if not updated_files.get(lfh):
                os.remove(local_files[lfh])
                continue
            old_path = local_files[lfh]
            new_path = updated_files[lfh]
            try:
                dest_folder = os.path.dirname(new_path)
                os.makedirs(dest_folder, exist_ok=True)
                shutil.move(old_path, new_path)
            except: pass

        for root, dirs, files in os.walk(self._destination, topdown=False):
            for folder in dirs:
                full_path = os.path.join(root, folder)
                # Якщо папка порожня — видаляємо
                if not os.listdir(full_path):
                    os.rmdir(full_path)

        self._bitfield = BitField(ceil(seed.length / seed.piece_length), seed.version)
        self._files = [(i[0], i[1], i[2]) for i in seed.files]
        self._data_count_per_piece = seed.piece_length
        self._full_length = seed.length

        for i in range(len(self._bitfield)):
            try:
                data = self.read_piece(i)
                print(hashlib.sha1(data[:]).digest() == seed.pieces[i * 20: i * 20 + 20], "SET\n\n\n\n\n")

                if hashlib.sha1(data[:]).digest() == seed.pieces[i * 20: i * 20 + 20]:
                    self._bitfield.set(i)
            except FileNotFoundError:
                pass


    def get_status(self) -> list[tuple[str, float]]:
        """
        Повертає список з інформацією про шлях до кожного файлу та відсоток його завантаження.
        """
        status_list = []
        total = 0
        for file_size, filepath, _ in self._files:
            start_index = total
            end_index = total + file_size

            # Підрахунок кількості повністю завантажених байтів у межах цього файлу
            loaded_bytes = 0
            for i in range(len(self._bitfield)):
                piece_start = i * self._data_count_per_piece
                piece_end = piece_start + self._data_count_per_piece
                if not (piece_end <= start_index or piece_start >= end_index):  # перекриває файл
                    if self._bitfield[i]:
                        overlap_start = max(piece_start, start_index)
                        overlap_end = min(piece_end, end_index)
                        loaded_bytes += overlap_end - overlap_start

            percent_loaded = (loaded_bytes / file_size) * 100 if file_size else 0
            status_list.append((os.path.join(self._destination, filepath), round(percent_loaded, 2)))
            total += file_size

        return status_list



    @property
    def bitfield(self):
        return self._bitfield

    @classmethod
    def open(cls, destination: str, files: typing.Sequence[tuple[int, str]],
             length_piece: int, pieces_hashes: bytes, version: int) -> typing.Self:
        full_length = sum([file[0] for file in files])
        bitfield = BitField(ceil(full_length / length_piece), version)

        obj = cls(full_length=full_length, bitfield=bitfield, block_size=length_piece,
                  destination=destination, files=files)

        for i in range(len(bitfield)):
            try:
                data = obj.read_piece(i)
                if hashlib.sha1(data[:]).digest() == pieces_hashes[i * 20: i * 20 + 20]:
                    obj.bitfield.set(i)
            except FileNotFoundError:
                pass
        return obj




