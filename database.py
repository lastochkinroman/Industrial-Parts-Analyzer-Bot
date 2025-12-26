import mysql.connector
from mysql.connector import Error, pooling
from config import Config
import logging
import json

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self):
        self.connection_pool = None
        self.init_pool()
        self.create_tables()

    def init_pool(self):
        """Инициализация пула соединений"""
        try:
            self.connection_pool = pooling.MySQLConnectionPool(
                **Config.MYSQL_CONFIG
            )
            logger.info("Database connection pool created successfully")
        except Error as e:
            logger.error(f"Error creating connection pool: {e}")
            raise

    def get_connection(self):
        """Получение соединения из пула"""
        try:
            return self.connection_pool.get_connection()
        except Error as e:
            logger.error(f"Error getting connection: {e}")
            raise

    def create_tables(self):
        """Создание таблиц в базе данных"""
        create_tables_queries = [
            """
            CREATE TABLE IF NOT EXISTS parts (
                id INT AUTO_INCREMENT PRIMARY KEY,
                part_number VARCHAR(50) UNIQUE NOT NULL,
                name VARCHAR(255),
                description TEXT,
                brands JSON,
                analogs JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_part_number (part_number)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS suppliers (
                id INT AUTO_INCREMENT PRIMARY KEY,
                code VARCHAR(20) UNIQUE NOT NULL,
                name VARCHAR(100),
                website VARCHAR(255),
                is_active BOOLEAN DEFAULT TRUE,
                INDEX idx_code (code)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS price_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                part_number VARCHAR(50) NOT NULL,
                supplier_code VARCHAR(20) NOT NULL,
                brand VARCHAR(100),
                price DECIMAL(10,2),
                delivery_days INT,
                currency VARCHAR(3) DEFAULT 'RUB',
                found_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (part_number) REFERENCES parts(part_number),
                INDEX idx_part_supplier (part_number, supplier_code),
                INDEX idx_found_at (found_at)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS search_requests (
                id INT AUTO_INCREMENT PRIMARY KEY,
                telegram_user_id BIGINT,
                telegram_username VARCHAR(100),
                part_numbers JSON,
                suppliers JSON,
                results_count INT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_user_id (telegram_user_id),
                INDEX idx_created_at (created_at)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS analysis_results (
                id INT AUTO_INCREMENT PRIMARY KEY,
                request_id INT,
                part_number VARCHAR(50),
                min_price DECIMAL(10,2),
                min_price_supplier VARCHAR(20),
                median_price DECIMAL(10,2),
                median_price_supplier VARCHAR(20),
                ai_analysis TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (request_id) REFERENCES search_requests(id),
                INDEX idx_part_number (part_number),
                INDEX idx_created_at (created_at)
            )
            """
        ]

        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            for query in create_tables_queries:
                cursor.execute(query)

            suppliers = [
                ('industrialsupply', 'IndustrialSupply.ru', 'https://industrialsupply.ru'),
                ('machineparts', 'MachineParts.com', 'https://machineparts.com'),
                ('factorystock', 'FactoryStock.eu', 'https://factorystock.eu')
            ]

            insert_supplier_query = """
            INSERT IGNORE INTO suppliers (code, name, website)
            VALUES (%s, %s, %s)
            """

            cursor.executemany(insert_supplier_query, suppliers)

            cursor.close()
            conn.commit()
            logger.info("Database tables created and initialized successfully")

        except Error as e:
            logger.error(f"Error creating tables: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()

    def save_part_data(self, part_data):
        """Сохранение данных о запчасти"""
        query = """
        INSERT INTO parts (part_number, name, description, brands, analogs)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            name = VALUES(name),
            description = VALUES(description),
            brands = VALUES(brands),
            analogs = VALUES(analogs),
            updated_at = CURRENT_TIMESTAMP
        """

        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute(query, (
                part_data['part_number'],
                part_data['name'],
                part_data['description'],
                json.dumps(part_data['brands']),
                json.dumps(part_data['analogs'])
            ))

            cursor.close()
            conn.commit()

            # Сохранение цен
            self.save_prices(part_data)

            return True
        except Error as e:
            logger.error(f"Error saving part data: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()

    def save_prices(self, part_data):
        """Сохранение цен в историю"""
        query = """
        INSERT INTO price_history
        (part_number, supplier_code, brand, price, delivery_days)
        VALUES (%s, %s, %s, %s, %s)
        """

        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            for supplier, prices in part_data['prices'].items():
                for price_data in prices:
                    cursor.execute(query, (
                        part_data['part_number'],
                        supplier,
                        price_data['brand'],
                        price_data['price'],
                        price_data['delivery']
                    ))

            cursor.close()
            conn.commit()
        except Error as e:
            logger.error(f"Error saving prices: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()

    def get_part_history(self, part_number, days=30):
        """Получение истории цен за период"""
        query = """
        SELECT
            ph.part_number,
            s.name as supplier_name,
            ph.brand,
            ph.price,
            ph.delivery_days,
            DATE(ph.found_at) as date
        FROM price_history ph
        JOIN suppliers s ON ph.supplier_code = s.code
        WHERE ph.part_number = %s
            AND ph.found_at >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
        ORDER BY ph.found_at DESC
        """

        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query, (part_number, days))
            results = cursor.fetchall()
            cursor.close()
            return results
        except Error as e:
            logger.error(f"Error getting part history: {e}")
            return []
        finally:
            if conn:
                conn.close()

db_manager = DatabaseManager()
