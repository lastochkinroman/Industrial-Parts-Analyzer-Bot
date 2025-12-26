from config import Config
from database import db_manager
import logging
import json
from typing import List, Dict, Any
import re

logger = logging.getLogger(__name__)

class PartsAnalyzer:
    def __init__(self):
        self.supplier_mapping = {
            'industrialsupply': 'IndustrialSupply.ru',
            'machineparts': 'MachineParts.com',
            'factorystock': 'FactoryStock.eu'
        }

    def extract_search_params(self, message_text: str):
        """Извлечение параметров поиска из сообщения"""
        suppliers = []
        if re.search(r'!industrialsupply|!isup', message_text, re.IGNORECASE):
            suppliers.append('industrialsupply')
        if re.search(r'!machineparts|!mp', message_text, re.IGNORECASE):
            suppliers.append('machineparts')
        if re.search(r'!factorystock|!fs', message_text, re.IGNORECASE):
            suppliers.append('factorystock')

        if not suppliers:
            suppliers = list(self.supplier_mapping.keys())

        cleaned_text = re.sub(r'![a-zA-Z]+', '', message_text)
        part_numbers = [
            pn.strip().upper()
            for pn in cleaned_text.split(',')
            if pn.strip()
        ]

        return part_numbers, suppliers

    async def search_parts(self, part_numbers: List[str], suppliers: List[str]):
        """Поиск информации по запчастям"""
        results = []

        for part_number in part_numbers:
            try:
                part_data = await self._mock_supplier_search(part_number, suppliers)

                if part_data:
                    # Сохраняем в базу
                    db_manager.save_part_data(part_data)
                    results.append(part_data)

            except Exception as e:
                logger.error(f"Error searching part {part_number}: {e}")
                continue

        return results

    async def _mock_supplier_search(self, part_number: str, suppliers: List[str]):
        """Имитация поиска у поставщиков"""
        mock_database = {
            "BP-12345-67890": {
                "part_number": "BP-12345-67890",
                "name": "Подшипник радиальный шариковый 6205",
                "description": "Подшипник шариковый радиальный 6205, 25x52x15мм",
                "brands": ["SKF", "FAG", "NSK"],
                "analogs": ["BP-12345-67891", "BP-12345-67892", "BP-6205-2RS"],
                "prices": {}
            },
            "MC-54321-09876": {
                "part_number": "MC-54321-09876",
                "name": "Муфта упругая втулочно-пальцевая",
                "description": "Муфта упругая втулочно-пальцевая МУВП-45",
                "brands": ["Siemens", "Rexnord", "Dodge"],
                "analogs": ["MC-54321-09877", "MC-54321-09878", "MC-MUVP-45"],
                "prices": {}
            }
        }

        base_data = mock_database.get(part_number, {
            "part_number": part_number,
            "name": f"Промышленная запчасть {part_number}",
            "description": f"Запчасть для промышленного оборудования {part_number}",
            "brands": ["Generic", "Standard"],
            "analogs": [f"{part_number}-A", f"{part_number}-B"],
            "prices": {}
        })

        import hashlib

        for supplier in suppliers:
            base_data["prices"][supplier] = []

            for i, brand in enumerate(base_data["brands"][:2]):  # Первые 2 бренда
                hash_input = f"{part_number}{supplier}{brand}{i}".encode()
                hash_val = int(hashlib.md5(hash_input).hexdigest(), 16)

                price = 10000 + (hash_val % 40000)  # 10000-50000
                delivery = 1 + (hash_val % 14)  # 1-14 дней

                base_data["prices"][supplier].append({
                    "brand": brand,
                    "price": price,
                    "delivery": delivery
                })

        return base_data

    def analyze_prices(self, part_data: Dict[str, Any]):
        """Анализ ценовых данных"""
        all_prices = []

        for supplier, prices in part_data["prices"].items():
            for price_info in prices:
                all_prices.append({
                    **price_info,
                    "supplier": supplier,
                    "supplier_name": self.supplier_mapping.get(supplier, supplier)
                })

        if not all_prices:
            return None

        sorted_prices = sorted(all_prices, key=lambda x: x["price"])

        min_price = sorted_prices[0]

        median_index = len(sorted_prices) // 2
        median_price = sorted_prices[median_index]

        analogs_analysis = []
        for analog in part_data["analogs"][:3]:  # Берем первые 3 аналога
            analogs_analysis.append({
                "part_number": analog,
                "estimated_price": min_price["price"] * 0.9 + (hash(analog) % 2000),
                "availability": "Есть в наличии" if hash(analog) % 2 == 0 else "Под заказ"
            })

        return {
            "part_number": part_data["part_number"],
            "name": part_data["name"],
            "min_price": min_price,
            "median_price": median_price,
            "all_prices": all_prices,
            "analogs": analogs_analysis,
            "brands": part_data["brands"]
        }

analyzer = PartsAnalyzer()
