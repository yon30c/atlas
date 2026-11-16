"""Backups cifrados y verificables de la base de conversaciones."""

import hashlib
import os
from pathlib import Path
import secrets
import sqlite3
import stat
import tempfile

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from atlas.adapters.sqlite.conversation_migrations import CONVERSATION_MIGRATIONS
from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.core.errors import ContractError


_MAGIC = b"ATLAS-CONVERSATION-BACKUP\x01"
_SALT_BYTES = 16
_NONCE_BYTES = 12


class ConversationBackup:
    """Snapshots SQLite cifrados con scrypt + AES-256-GCM."""

    def __init__(self, database: SQLiteDatabase) -> None:
        if not isinstance(database, SQLiteDatabase):
            raise ContractError("database debe ser SQLiteDatabase")
        self._database = database

    @staticmethod
    def _derive_key(passphrase: str, salt: bytes) -> bytes:
        if not isinstance(passphrase, str) or len(passphrase) < 12:
            raise ContractError("la contraseña del respaldo debe tener al menos 12 caracteres")
        return hashlib.scrypt(passphrase.encode("utf-8"), salt=salt, n=2**15, r=8, p=1, dklen=32)

    @classmethod
    def _decrypt(cls, payload: bytes, passphrase: str) -> bytes:
        header_size = len(_MAGIC) + _SALT_BYTES + _NONCE_BYTES
        if not isinstance(payload, bytes) or len(payload) <= header_size or not payload.startswith(_MAGIC):
            raise ContractError("formato de respaldo Atlas no reconocido")
        offset = len(_MAGIC)
        salt = payload[offset:offset + _SALT_BYTES]
        nonce_start = offset + _SALT_BYTES
        nonce = payload[nonce_start:nonce_start + _NONCE_BYTES]
        try:
            return AESGCM(cls._derive_key(passphrase, salt)).decrypt(
                nonce, payload[nonce_start + _NONCE_BYTES:], _MAGIC,
            )
        except Exception as exc:
            raise ContractError("contraseña incorrecta o respaldo alterado") from exc

    @staticmethod
    def _validate_snapshot(data: bytes) -> None:
        with tempfile.NamedTemporaryFile(prefix="atlas-verify-", suffix=".sqlite3") as temp:
            temp.write(data)
            temp.flush()
            connection = sqlite3.connect(f"file:{temp.name}?mode=ro", uri=True)
            try:
                if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ContractError("integridad SQLite del respaldo no válida")
                tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                required = {"schema_migrations", "conversations", "conversation_messages", "conversation_state"}
                if not required <= tables:
                    raise ContractError("el respaldo no contiene el esquema de conversaciones Atlas")
                applied = connection.execute("SELECT version, name, checksum FROM schema_migrations ORDER BY version").fetchall()
                expected = [(m.version, m.name, m.checksum) for m in CONVERSATION_MIGRATIONS]
                if applied != expected:
                    raise ContractError("el historial de migraciones del respaldo no coincide")
            finally:
                connection.close()

    def create(self, destination: str | Path, passphrase: str) -> Path:
        """Crea un backup cifrado sin sobrescribir un archivo existente."""
        target = Path(destination).expanduser()
        if not target.is_absolute() or not target.parent.is_dir():
            raise ContractError("el destino del respaldo debe ser absoluto y su directorio debe existir")
        if not isinstance(passphrase, str) or len(passphrase) < 12:
            raise ContractError("la contraseña del respaldo debe tener al menos 12 caracteres")
        fd, snapshot_path = tempfile.mkstemp(prefix=".atlas-snapshot-", suffix=".sqlite3", dir=self._database.path.parent)
        os.fchmod(fd, 0o600)
        os.close(fd)
        try:
            with self._database.connection() as source:
                target_db = sqlite3.connect(snapshot_path)
                try:
                    source.backup(target_db)
                finally:
                    target_db.close()
            snapshot = Path(snapshot_path).read_bytes()
            self._validate_snapshot(snapshot)
            salt, nonce = secrets.token_bytes(_SALT_BYTES), secrets.token_bytes(_NONCE_BYTES)
            ciphertext = AESGCM(self._derive_key(passphrase, salt)).encrypt(nonce, snapshot, _MAGIC)
            payload = _MAGIC + salt + nonce + ciphertext
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            output_fd = os.open(target, flags, 0o600)
            try:
                os.fchmod(output_fd, 0o600)
                view = memoryview(payload)
                while view:
                    written = os.write(output_fd, view)
                    view = view[written:]
                os.fsync(output_fd)
            finally:
                os.close(output_fd)
            return target
        except FileExistsError as exc:
            raise ContractError("el archivo de respaldo ya existe; no se sobrescribirá") from exc
        except OSError as exc:
            raise ContractError("no se pudo crear el respaldo cifrado") from exc
        finally:
            try:
                os.unlink(snapshot_path)
            except FileNotFoundError:
                pass

    def verify(self, source: str | Path, passphrase: str) -> None:
        try:
            payload = Path(source).expanduser().read_bytes()
        except OSError as exc:
            raise ContractError("no se pudo leer el archivo de respaldo") from exc
        self._validate_snapshot(self._decrypt(payload, passphrase))

    def restore_to(self, source: str | Path, passphrase: str, destination: str | Path) -> Path:
        """Restaura a una base nueva dentro de un directorio privado."""
        target = Path(destination).expanduser()
        if not target.is_absolute() or target.exists() or target.is_symlink():
            raise ContractError("la restauración requiere una ruta absoluta que no exista")
        try:
            info = target.parent.lstat()
        except OSError as exc:
            raise ContractError("el directorio de destino debe existir") from exc
        if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077:
            raise ContractError("el directorio de restauración debe ser privado (0700)")
        if hasattr(os, "getuid") and info.st_uid != os.getuid():
            raise ContractError("el directorio de restauración debe pertenecer al usuario actual")
        try:
            payload = Path(source).expanduser().read_bytes()
        except OSError as exc:
            raise ContractError("no se pudo leer el respaldo") from exc
        snapshot = self._decrypt(payload, passphrase)
        self._validate_snapshot(snapshot)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(target, flags, 0o600)
        except OSError as exc:
            raise ContractError("no se pudo crear la base restaurada sin sobrescribir archivos") from exc
        try:
            os.fchmod(fd, 0o600)
            view = memoryview(snapshot)
            while view:
                written = os.write(fd, view)
                view = view[written:]
            os.fsync(fd)
        except Exception:
            try:
                os.unlink(target)
            except FileNotFoundError:
                pass
            raise
        finally:
            os.close(fd)
        return target
