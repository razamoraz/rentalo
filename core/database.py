import sqlite3
from pathlib import Path
from typing import Optional, Union, List, Dict
from core.models import Room, Lease, Payment


class DatabaseManager:
    def __init__(self, db_path: Union[str, Path] = "rentafacil.db"):
        self.db_path = str(db_path)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON;")
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _init_db(self) -> None:
        with self.conn:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS rooms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    default_rent REAL NOT NULL,
                    is_occupied INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS leases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
                    tenant_name TEXT NOT NULL,
                    tenant_phone TEXT NOT NULL,
                    monthly_rent REAL NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    deposit_amount REAL NOT NULL DEFAULT 0.0,
                    initial_rent REAL
                );

                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lease_id INTEGER NOT NULL REFERENCES leases(id) ON DELETE CASCADE,
                    billing_year INTEGER NOT NULL,
                    billing_month INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    paid_date TEXT NOT NULL,
                    proof_image_path TEXT,
                    payment_method TEXT DEFAULT 'TRANSFERENCIA',
                    UNIQUE(lease_id, billing_year, billing_month)
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
            """)

            # Migración automática en bases de datos existentes
            cursor = self.conn.execute("PRAGMA table_info(leases)")
            existing_cols = [r["name"] for r in cursor.fetchall()]
            if "deposit_amount" not in existing_cols:
                self.conn.execute("ALTER TABLE leases ADD COLUMN deposit_amount REAL NOT NULL DEFAULT 0.0")
            if "initial_rent" not in existing_cols:
                self.conn.execute("ALTER TABLE leases ADD COLUMN initial_rent REAL")

            cursor_pay = self.conn.execute("PRAGMA table_info(payments)")
            pay_cols = [r["name"] for r in cursor_pay.fetchall()]
            if "proof_image_path" not in pay_cols:
                self.conn.execute("ALTER TABLE payments ADD COLUMN proof_image_path TEXT")
            if "payment_method" not in pay_cols:
                self.conn.execute("ALTER TABLE payments ADD COLUMN payment_method TEXT DEFAULT 'TRANSFERENCIA'")

    # ---------------------------------------------------------
    # ROOMS CRUD
    # ---------------------------------------------------------
    def create_room(self, name: str, default_rent: float) -> Room:
        with self.conn:
            cursor = self.conn.execute(
                "INSERT INTO rooms (name, default_rent, is_occupied) VALUES (?, ?, 0)",
                (name, float(default_rent))
            )
            room_id = cursor.lastrowid
        return Room(id=room_id, name=name, default_rent=float(default_rent), is_occupied=False)

    def get_room(self, room_id: int) -> Optional[Room]:
        cursor = self.conn.execute("SELECT * FROM rooms WHERE id = ?", (room_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return Room(
            id=row["id"],
            name=row["name"],
            default_rent=row["default_rent"],
            is_occupied=bool(row["is_occupied"])
        )

    def get_all_rooms(self) -> List[Room]:
        cursor = self.conn.execute("SELECT * FROM rooms ORDER BY id ASC")
        rows = cursor.fetchall()
        return [
            Room(
                id=r["id"],
                name=r["name"],
                default_rent=r["default_rent"],
                is_occupied=bool(r["is_occupied"])
            )
            for r in rows
        ]

    def update_room(
        self,
        room_id: int,
        name: Optional[str] = None,
        default_rent: Optional[float] = None,
        is_occupied: Optional[bool] = None
    ) -> Room:
        room = self.get_room(room_id)
        if not room:
            raise ValueError(f"Cuarto con ID {room_id} no encontrado.")

        new_name = name if name is not None else room.name
        new_rent = float(default_rent) if default_rent is not None else room.default_rent
        new_occupied = is_occupied if is_occupied is not None else room.is_occupied

        with self.conn:
            self.conn.execute(
                "UPDATE rooms SET name = ?, default_rent = ?, is_occupied = ? WHERE id = ?",
                (new_name, new_rent, 1 if new_occupied else 0, room_id)
            )

        return Room(id=room_id, name=new_name, default_rent=new_rent, is_occupied=new_occupied)

    def delete_room(self, room_id: int) -> bool:
        with self.conn:
            cursor = self.conn.execute("DELETE FROM rooms WHERE id = ?", (room_id,))
            return cursor.rowcount > 0

    # ---------------------------------------------------------
    # LEASES
    # ---------------------------------------------------------
    def start_lease(
        self,
        room_id: int,
        tenant_name: str,
        tenant_phone: str,
        monthly_rent: float,
        start_date: str,
        deposit_amount: float = 0.0,
        initial_rent: Optional[float] = None
    ) -> Lease:
        room = self.get_room(room_id)
        if not room:
            raise ValueError(f"Cuarto con ID {room_id} no existe.")

        if room.is_occupied:
            raise ValueError(f"El cuarto '{room.name}' ya está ocupado.")

        active_lease = self.get_active_lease_for_room(room_id)
        if active_lease:
            raise ValueError(f"El cuarto '{room.name}' ya tiene un contrato activo.")

        with self.conn:
            cursor = self.conn.execute(
                """
                INSERT INTO leases (room_id, tenant_name, tenant_phone, monthly_rent, start_date, end_date, is_active, deposit_amount, initial_rent)
                VALUES (?, ?, ?, ?, ?, NULL, 1, ?, ?)
                """,
                (
                    room_id,
                    tenant_name,
                    tenant_phone,
                    float(monthly_rent),
                    start_date,
                    float(deposit_amount),
                    float(initial_rent) if initial_rent is not None else None
                )
            )
            lease_id = cursor.lastrowid
            self.conn.execute("UPDATE rooms SET is_occupied = 1 WHERE id = ?", (room_id,))

        return Lease(
            id=lease_id,
            room_id=room_id,
            tenant_name=tenant_name,
            tenant_phone=tenant_phone,
            monthly_rent=float(monthly_rent),
            start_date=start_date,
            end_date=None,
            is_active=True,
            deposit_amount=float(deposit_amount),
            initial_rent=float(initial_rent) if initial_rent is not None else None
        )

    def end_lease(self, lease_id: int, end_date: str) -> Lease:
        lease = self.get_lease(lease_id)
        if not lease:
            raise ValueError(f"Contrato con ID {lease_id} no encontrado.")

        with self.conn:
            self.conn.execute(
                "UPDATE leases SET is_active = 0, end_date = ? WHERE id = ?",
                (end_date, lease_id)
            )
            self.conn.execute("UPDATE rooms SET is_occupied = 0 WHERE id = ?", (lease.room_id,))

        return Lease(
            id=lease.id,
            room_id=lease.room_id,
            tenant_name=lease.tenant_name,
            tenant_phone=lease.tenant_phone,
            monthly_rent=lease.monthly_rent,
            start_date=lease.start_date,
            end_date=end_date,
            is_active=False,
            deposit_amount=lease.deposit_amount,
            initial_rent=lease.initial_rent
        )

    def update_lease(
        self,
        lease_id: int,
        tenant_name: Optional[str] = None,
        tenant_phone: Optional[str] = None,
        monthly_rent: Optional[float] = None,
        deposit_amount: Optional[float] = None,
        start_date: Optional[str] = None,
        initial_rent: Optional[float] = None
    ) -> Lease:
        lease = self.get_lease(lease_id)
        if not lease:
            raise ValueError(f"Contrato con ID {lease_id} no encontrado.")

        new_name = tenant_name.strip() if tenant_name is not None else lease.tenant_name
        new_phone = tenant_phone.strip() if tenant_phone is not None else lease.tenant_phone
        new_rent = float(monthly_rent) if monthly_rent is not None else lease.monthly_rent
        new_deposit = float(deposit_amount) if deposit_amount is not None else lease.deposit_amount
        new_start = start_date.strip() if start_date is not None else lease.start_date
        new_initial = float(initial_rent) if initial_rent is not None else lease.initial_rent

        with self.conn:
            self.conn.execute(
                """
                UPDATE leases
                SET tenant_name = ?, tenant_phone = ?, monthly_rent = ?, deposit_amount = ?, start_date = ?, initial_rent = ?
                WHERE id = ?
                """,
                (new_name, new_phone, new_rent, new_deposit, new_start, new_initial, lease_id)
            )

        updated = self.get_lease(lease_id)
        if not updated:
            raise ValueError(f"Error al recuperar contrato actualizado {lease_id}.")
        return updated

    def _row_to_lease(self, row: sqlite3.Row) -> Lease:
        row_keys = row.keys()
        return Lease(
            id=row["id"],
            room_id=row["room_id"],
            tenant_name=row["tenant_name"],
            tenant_phone=row["tenant_phone"],
            monthly_rent=row["monthly_rent"],
            start_date=row["start_date"],
            end_date=row["end_date"],
            is_active=bool(row["is_active"]),
            deposit_amount=row["deposit_amount"] if "deposit_amount" in row_keys and row["deposit_amount"] is not None else 0.0,
            initial_rent=row["initial_rent"] if "initial_rent" in row_keys else None
        )

    def get_lease(self, lease_id: int) -> Optional[Lease]:
        cursor = self.conn.execute("SELECT * FROM leases WHERE id = ?", (lease_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_lease(row)

    def get_active_lease_for_room(self, room_id: int) -> Optional[Lease]:
        cursor = self.conn.execute(
            "SELECT * FROM leases WHERE room_id = ? AND is_active = 1 LIMIT 1",
            (room_id,)
        )
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_lease(row)

    def get_all_leases(self, active_only: bool = False) -> List[Lease]:
        query = "SELECT * FROM leases"
        params = ()
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY id ASC"
        cursor = self.conn.execute(query, params)
        return [self._row_to_lease(r) for r in cursor.fetchall()]

    # ---------------------------------------------------------
    # PAYMENTS
    # ---------------------------------------------------------
    def _row_to_payment(self, row: sqlite3.Row) -> Payment:
        row_keys = row.keys()
        return Payment(
            id=row["id"],
            lease_id=row["lease_id"],
            billing_year=row["billing_year"],
            billing_month=row["billing_month"],
            amount=row["amount"],
            paid_date=row["paid_date"],
            proof_image_path=row["proof_image_path"] if "proof_image_path" in row_keys else None,
            payment_method=row["payment_method"] if "payment_method" in row_keys and row["payment_method"] is not None else "TRANSFERENCIA"
        )

    def record_payment(
        self,
        lease_id: int,
        billing_year: int,
        billing_month: int,
        amount: float,
        paid_date: str,
        proof_image_path: Optional[str] = None,
        payment_method: str = "TRANSFERENCIA"
    ) -> Payment:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO payments (lease_id, billing_year, billing_month, amount, paid_date, proof_image_path, payment_method)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(lease_id, billing_year, billing_month)
                DO UPDATE SET
                    amount = excluded.amount,
                    paid_date = excluded.paid_date,
                    proof_image_path = COALESCE(excluded.proof_image_path, payments.proof_image_path),
                    payment_method = excluded.payment_method
                """,
                (lease_id, int(billing_year), int(billing_month), float(amount), paid_date, proof_image_path, payment_method)
            )

        return self.get_payment(lease_id, billing_year, billing_month)

    def get_payment(self, lease_id: int, billing_year: int, billing_month: int) -> Optional[Payment]:
        cursor = self.conn.execute(
            """
            SELECT * FROM payments
            WHERE lease_id = ? AND billing_year = ? AND billing_month = ?
            LIMIT 1
            """,
            (lease_id, int(billing_year), int(billing_month))
        )
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_payment(row)

    def get_payments_for_lease(self, lease_id: int) -> List[Payment]:
        cursor = self.conn.execute(
            "SELECT * FROM payments WHERE lease_id = ? ORDER BY billing_year ASC, billing_month ASC",
            (lease_id,)
        )
        return [self._row_to_payment(r) for r in cursor.fetchall()]

    def get_all_payments(self) -> List[Payment]:
        cursor = self.conn.execute(
            "SELECT * FROM payments ORDER BY paid_date DESC, id DESC"
        )
        return [self._row_to_payment(r) for r in cursor.fetchall()]

    # ---------------------------------------------------------
    # SETTINGS
    # ---------------------------------------------------------
    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        cursor = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        if row:
            return row["value"]
        return default

    def set_setting(self, key: str, value: str) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, str(value))
            )

    def get_all_settings(self) -> Dict[str, str]:
        cursor = self.conn.execute("SELECT key, value FROM settings")
        return {r["key"]: r["value"] for r in cursor.fetchall()}
