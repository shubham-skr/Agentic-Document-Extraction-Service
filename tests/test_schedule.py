import asyncio
from app.extraction import extract_rent_schedule_fields, llm_extract

LEASE_SCHEMA = {
    "name": "lease_abstraction",
    "fields": {
        "rent_schedule_start_dates": {"name": "Rent schedule start dates", "description": "List the beginning date of each base rent period."},
        "rent_schedule_end_dates": {"name": "Rent schedule end dates", "description": "List the ending date of each base rent period."},
        "rent_schedule_monthly_rent": {"name": "Rent schedule monthly rent", "description": "List the monthly base rent for each period."},
        "total_base_rent": {"name": "Total base rent", "description": "Sum of all base rent due over the lease term."},
    },
}


def test_schedule_parser_recovers_every_period_and_total_from_ocr_table():
    source = """===== PAGE 3 OCR =====
    1. BASE RENT SCHEDULE
    August 1, 2010 through July 31, 2011 $11,934.00
    August 1, 2011 through July 31, 2012 $12,196.00
    August 1, 2012 through July 31, 2013 $12,458.00
    August 1, 2013 through July 31, 2014 $12,720.00
    August 1, 2014 through July 31, 2015 $12,982.00
    August 1, 2015 through July 31, 2016 $13,244.00
    August 1, 2016 through July 31, 2017 $13,506.00
    August 1, 2017 through July 31, 2018 $13,768.00
    August 1, 2018 through July 31, 2019 $14,030.00
    August 1, 2019 through July 31, 2020 $14,292.00
    August 1, 2020 through February 28, 2021 $14,554.00
    """
    result = extract_rent_schedule_fields({"text": source}, LEASE_SCHEMA, {})
    assert len(result["rent_schedule_start_dates"]["value"]) == 11
    assert result["rent_schedule_start_dates"]["value"][0] == "2010-08-01"
    assert result["rent_schedule_end_dates"]["value"][-1] == "2021-02-28"
    assert result["rent_schedule_monthly_rent"]["value"][-1] == 14554.0
    assert result["total_base_rent"]["value"] == 1675438.0
    assert "[Page 3]" in result["total_base_rent"]["citation"]


def test_schedule_parser_uses_monthly_column_not_annual_amount():
    source = """===== PAGE 18 OCR =====
    BASE RENT SCHEDULE ANNUAL RENT MONTHLY RENT MONTHS
    05/01/93 - 04/30/94 $ 23,184 $ 1,932 12 $ 23,184
    05/01/94 - 04/30/95 $ 23,880 $ 1,990 12 $ 23,880
    05/01/95 - 04/30/96 $ 24,600 $ 2,050 12 $ 24,600
    05/01/96 - 04/30/97 $ 25,332 $ 2,111 12 $ 25,332
    05/01/97 - 04/30/98 $ 26,088 $ 2,174 12 $ 26,088
    """
    result = extract_rent_schedule_fields({"text": source}, LEASE_SCHEMA, {})
    assert result["rent_schedule_monthly_rent"]["value"] == [1932.0, 1990.0, 2050.0, 2111.0, 2174.0]
    assert result["total_base_rent"]["value"] == 123084.0


def test_schedule_only_schema_does_not_call_the_llm():
    source = """1. BASE RENT SCHEDULE
    October 1, 2025 through April 30, 2027 $2,845.00
    """
    class NoCallLLM:
        calls = 0
        async def complete(self, *args, **kwargs):
            self.calls += 1
            raise AssertionError("schedule-only extraction should be deterministic")

    schema = {"name": "lease_abstraction", "fields": LEASE_SCHEMA["fields"]}
    llm = NoCallLLM()
    entries = asyncio.run(llm_extract(llm, schema, {}, {"kind": "docx", "text": source, "pages": []}, {}))
    assert llm.calls == 0
    assert entries[0]["rent_schedule_monthly_rent"]["value"] == [2845.0]
    assert entries[0]["total_base_rent"]["value"] == 54055.0
