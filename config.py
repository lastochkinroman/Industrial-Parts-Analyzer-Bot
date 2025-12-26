import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

    MISTRAL_API_KEY = os.getenv('MISTRAL_API_KEY')

    MYSQL_CONFIG = {
        'host': os.getenv('MYSQL_HOST', 'VH301.spaceweb.ru'),
        'user': os.getenv('MYSQL_USER', 'romablunt_porf'),
        'password': os.getenv('MYSQL_PASSWORD', 'GXBVE5Mj6DR3C@SH'),
        'database': os.getenv('MYSQL_DATABASE', 'romablunt_porf'),
        'port': 3306,
        'charset': 'utf8mb4',
        'autocommit': True,
        'pool_size': 5
    }

    SUPPLIER_APIS = {
        'industrialsupply': 'https://api.industrialsupply.ru/v1',
        'machineparts': 'https://api.machineparts.com/v1',
        'factorystock': 'https://api.factorystock.eu/v1'
    }
