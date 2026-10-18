# database.py - ИСПРАВЛЕННАЯ ВЕРСИЯ
# Ключевые изменения:
# 1. Добавлена функция get_groups_without_post() для получения групп НЕ добавленных в рассылку
# 2. Функция get_available_groups() теперь фильтрует активные группы
# 3. Функция get_groups_with_status() работает правильно

import sqlite3
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class BotDatabase:
    """Класс для работы с базой данных бота"""
    
    def __init__(self, db_path: str = "bot_database.db"):
        self.db_path = db_path
        self._init_tables()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Получение соединения с БД"""
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    
    def _init_tables(self) -> None:
        """Создание таблиц при первом запуске"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    is_blocked INTEGER DEFAULT 0,
                    created_at INTEGER NOT NULL
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS groups (
                    chat_id INTEGER PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    last_checked INTEGER
                )
            ''')

            # Миграция для уже существующих баз (созданных до появления is_active)
            cursor.execute("PRAGMA table_info(groups)")
            existing_columns = {row[1] for row in cursor.fetchall()}
            if "is_active" not in existing_columns:
                cursor.execute("ALTER TABLE groups ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
            if "last_checked" not in existing_columns:
                cursor.execute("ALTER TABLE groups ADD COLUMN last_checked INTEGER")
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    type TEXT NOT NULL CHECK(type IN ('send', 'forward')),
                    source_chat_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    interval INTEGER NOT NULL,
                    created_at INTEGER NOT NULL
                )
            ''')
            
            # Миграция: разовые рассылки (is_once = 1 — отправить один раз, без повтора)
            cursor.execute("PRAGMA table_info(posts)")
            post_columns = {row[1] for row in cursor.fetchall()}
            if "is_once" not in post_columns:
                cursor.execute("ALTER TABLE posts ADD COLUMN is_once INTEGER NOT NULL DEFAULT 0")

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS post_groups (
                    post_id INTEGER,
                    chat_id INTEGER,
                    PRIMARY KEY (post_id, chat_id),
                    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
                    FOREIGN KEY (chat_id) REFERENCES groups(chat_id) ON DELETE CASCADE
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS admins (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    added_at INTEGER NOT NULL
                )
            ''')

            # WAL — база не блокируется, когда планировщик и кнопки пишут одновременно
            cursor.execute("PRAGMA journal_mode=WAL")

            conn.commit()
            logger.info("База данных инициализирована")
    
    # ========== РАБОТА С ПОЛЬЗОВАТЕЛЯМИ ==========
    
    def add_user(self, user_id: int) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO users (user_id, created_at)
                VALUES (?, ?)
            ''', (user_id, int(datetime.now().timestamp())))
            conn.commit()
    
    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_all_users(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE is_blocked = 0')
            return [dict(row) for row in cursor.fetchall()]
    
    def get_all_users_with_blocked(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users')
            return [dict(row) for row in cursor.fetchall()]
    
    def update_user_blocked(self, user_id: int, is_blocked: int) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users SET is_blocked = ? WHERE user_id = ?
            ''', (is_blocked, user_id))
            conn.commit()
    
    def delete_user(self, user_id: int) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
            conn.commit()
    
    # ========== АДМИНЫ ==========

    def get_admins(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM admins ORDER BY added_at')
            return [dict(row) for row in cursor.fetchall()]

    def add_admin(self, user_id: int, username: Optional[str]) -> None:
        with self._get_connection() as conn:
            conn.execute('''
                INSERT INTO admins (user_id, username, added_at) VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET username = excluded.username
            ''', (user_id, username, int(datetime.now().timestamp())))
            conn.commit()

    def remove_admin(self, user_id: int) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute('DELETE FROM admins WHERE user_id = ?', (user_id,))
            conn.commit()
            return cursor.rowcount > 0

    def get_admin_ids(self) -> set:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM admins')
            return {row[0] for row in cursor.fetchall()}

    # ========== РАБОТА С ГРУППАМИ ==========
    
    def add_group(self, chat_id: int, title: str) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO groups (chat_id, title, created_at, is_active)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(chat_id) DO UPDATE SET
                    title = excluded.title,
                    is_active = 1
            ''', (chat_id, title, int(datetime.now().timestamp())))
            conn.commit()
    
    def get_group(self, chat_id: int) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM groups WHERE chat_id = ?', (chat_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_all_groups(self, active_only: bool = False) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if active_only:
                cursor.execute('SELECT * FROM groups WHERE is_active = 1 ORDER BY title')
            else:
                cursor.execute('SELECT * FROM groups ORDER BY title')
            return [dict(row) for row in cursor.fetchall()]

    def get_broken_groups(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM groups WHERE is_active = 0 ORDER BY title')
            return [dict(row) for row in cursor.fetchall()]

    def set_group_status(self, chat_id: int, is_active: bool) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE groups SET is_active = ?, last_checked = ? WHERE chat_id = ?
            ''', (1 if is_active else 0, int(datetime.now().timestamp()), chat_id))
            conn.commit()

    def delete_broken_groups(self) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM groups WHERE is_active = 0')
            conn.commit()
            return cursor.rowcount

    def delete_broken_groups_from_posts(self) -> int:
        """Удаляет связи нерабочих групп (is_active = 0) с постами"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM post_groups WHERE chat_id IN (
                    SELECT chat_id FROM groups WHERE is_active = 0
                )
            ''')
            deleted_relations = cursor.rowcount
            conn.commit()
            return deleted_relations

    def cleanup_database(self) -> tuple:
        """Полная очистка базы: удаляет нерабочие группы и их связи с постами"""
        relations_deleted = self.delete_broken_groups_from_posts()
        groups_deleted = self.delete_broken_groups()
        return (groups_deleted, relations_deleted)
    
    def get_groups_with_status(self, post_id: int) -> List[Dict[str, Any]]:
        """Получить все активные группы с информацией о том, добавлены ли они в пост"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    g.*,
                    CASE WHEN pg.post_id IS NOT NULL THEN 1 ELSE 0 END as is_selected
                FROM groups g
                LEFT JOIN post_groups pg ON g.chat_id = pg.chat_id AND pg.post_id = ?
                WHERE g.is_active = 1
                ORDER BY g.title
            ''', (post_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_available_groups(self, post_id: int) -> List[Dict[str, Any]]:
        """Получить активные группы, которые ЕЩЕ НЕ добавлены в этот пост"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT g.* FROM groups g
                WHERE g.is_active = 1
                AND g.chat_id NOT IN (
                    SELECT chat_id FROM post_groups WHERE post_id = ?
                )
                ORDER BY g.title
            ''', (post_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_groups_without_post(self, post_id: int) -> List[Dict[str, Any]]:
        """Альтернатива get_available_groups - для совместимости"""
        return self.get_available_groups(post_id)
    
    def delete_group(self, chat_id: int) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM groups WHERE chat_id = ?', (chat_id,))
            conn.commit()
    
    def update_group_title(self, chat_id: int, title: str) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE groups SET title = ? WHERE chat_id = ?
            ''', (title, chat_id))
            conn.commit()
    
    # ========== РАБОТА С ПОСТАМИ ==========
    
    def create_post(self, title: str, post_type: str, source_chat_id: int, 
                    message_id: int, interval: int) -> int:
        """interval = 0 — разовая рассылка (is_once = 1), планировщик её не повторяет"""
        is_once = 1 if interval <= 0 else 0
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO posts (title, type, source_chat_id, message_id, interval, created_at, is_once)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (title, post_type, source_chat_id, message_id, max(interval, 0),
                  int(datetime.now().timestamp()), is_once))
            conn.commit()
            return cursor.lastrowid
    
    def get_post(self, post_id: int) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM posts WHERE id = ?', (post_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def post_exists(self, post_id: int) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1 FROM posts WHERE id = ?', (post_id,))
            return cursor.fetchone() is not None
    
    def get_all_posts(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM posts ORDER BY id DESC')
            return [dict(row) for row in cursor.fetchall()]
    
    def get_post_info(self, post_id: int) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    p.*,
                    COUNT(pg.chat_id) as groups_count
                FROM posts p
                LEFT JOIN post_groups pg ON p.id = pg.post_id
                WHERE p.id = ?
                GROUP BY p.id
            ''', (post_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def update_post_interval(self, post_id: int, new_interval: int) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE posts SET interval = ?, is_once = ? WHERE id = ?
            ''', (max(new_interval, 0), 1 if new_interval <= 0 else 0, post_id))
            conn.commit()
    
    def update_post_title(self, post_id: int, title: str) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE posts SET title = ? WHERE id = ?
            ''', (title, post_id))
            conn.commit()
    
    def update_post_created_at(self, post_id: int, created_at: int) -> None:
        """Обновление времени создания поста (для планировщика)"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE posts SET created_at = ? WHERE id = ?
            ''', (created_at, post_id))
            conn.commit()
    
    def delete_post(self, post_id: int) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM posts WHERE id = ?', (post_id,))
            conn.commit()
    
    # ========== РАБОТА СО СВЯЗЯМИ ==========
    
    def add_groups_to_post(self, post_id: int, chat_ids: List[int]) -> None:
        with self._get_connection() as conn:
            conn.executemany(
                'INSERT OR IGNORE INTO post_groups (post_id, chat_id) VALUES (?, ?)',
                [(post_id, c) for c in chat_ids]
            )
            conn.commit()

    def clear_post_groups(self, post_id: int) -> None:
        with self._get_connection() as conn:
            conn.execute('DELETE FROM post_groups WHERE post_id = ?', (post_id,))
            conn.commit()

    def add_group_to_post(self, post_id: int, chat_id: int) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO post_groups (post_id, chat_id)
                VALUES (?, ?)
            ''', (post_id, chat_id))
            conn.commit()
    
    def remove_group_from_post(self, post_id: int, chat_id: int) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM post_groups WHERE post_id = ? AND chat_id = ?
            ''', (post_id, chat_id))
            conn.commit()
    
    def get_post_groups(self, post_id: int) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT g.* FROM groups g
                INNER JOIN post_groups pg ON g.chat_id = pg.chat_id
                WHERE pg.post_id = ?
                ORDER BY g.title
            ''', (post_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_post_group_ids(self, post_id: int) -> List[int]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT chat_id FROM post_groups WHERE post_id = ?
            ''', (post_id,))
            return [row[0] for row in cursor.fetchall()]
    
    def get_post_groups_count(self, post_id: int) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) FROM post_groups WHERE post_id = ?
            ''', (post_id,))
            return cursor.fetchone()[0]
    
    def get_posts_for_group(self, chat_id: int) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT p.* FROM posts p
                INNER JOIN post_groups pg ON p.id = pg.post_id
                WHERE pg.chat_id = ?
                ORDER BY p.id DESC
            ''', (chat_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    # ========== СТАТИСТИКА ==========
    
    def get_users_count(self, include_blocked: bool = False) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if include_blocked:
                cursor.execute('SELECT COUNT(*) FROM users')
            else:
                cursor.execute('SELECT COUNT(*) FROM users WHERE is_blocked = 0')
            return cursor.fetchone()[0]
    
    def get_groups_count(self) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM groups')
            return cursor.fetchone()[0]
    
    def get_posts_count(self) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM posts')
            return cursor.fetchone()[0]


_db_instance = None

def get_database(db_path: Optional[str] = None) -> BotDatabase:
    global _db_instance
    if _db_instance is None:
        if db_path is None:
            from config import DB_PATH
            db_path = DB_PATH
        _db_instance = BotDatabase(db_path)
    return _db_instance
