import re
from typing import Optional, Dict

from app.schemas.final_reasoning_schema import TimePlan


class TimeResolver:
    def __init__(self, schema: Dict[str, str]):
        self.schema = schema
        self.date_columns = [
            col for col, dtype in schema.items()
            if "date" in col.lower() or "datetime" in dtype.lower()
        ]

    def resolve(self, question: str) -> Optional[TimePlan]:
        """
        Resolve time-related intent from a question.
        Returns a TimePlan or None.
        """

        if not self.date_columns:
            return None

        q = question.lower()
        date_col = self.date_columns[0]

        # -------------------------
        # YEAR (e.g., 2022)
        # -------------------------
        year_match = re.search(r"(20\d{2})", q)
        if year_match:
            year = year_match.group(1)
            return TimePlan(
                column=date_col,
                granularity="year",
                start=f"{year}-01-01",
                end=f"{year}-12-31",
            )

        # -------------------------
        # MONTH (e.g., March 2023)
        # -------------------------
        month_match = re.search(
            r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(20\d{2})",
            q,
        )
        if month_match:
            month_map = {
                "jan": "01", "feb": "02", "mar": "03", "apr": "04",
                "may": "05", "jun": "06", "jul": "07", "aug": "08",
                "sep": "09", "oct": "10", "nov": "11", "dec": "12",
            }
            month = month_map[month_match.group(1)]
            year = month_match.group(2)
            return TimePlan(
                column=date_col,
                granularity="month",
                start=f"{year}-{month}-01",
                end=f"{year}-{month}-31",
            )

        # -------------------------
        # RANGE (e.g., between 2020 and 2022)
        # -------------------------
        range_match = re.search(r"(20\d{2}).*(20\d{2})", q)
        if range_match:
            start, end = range_match.groups()
            return TimePlan(
                column=date_col,
                granularity="year",
                start=f"{start}-01-01",
                end=f"{end}-12-31",
            )

        return None
