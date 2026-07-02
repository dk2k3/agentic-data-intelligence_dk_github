"""
Automated evaluation suite — 150+ diverse NL questions.

Run with:   python -m pytest tests/test_pipeline.py -v

The tests use synthetic DataFrames so no real dataset upload is needed.
Each test validates that the pipeline produces an ExecutionPlan with the
expected intent and does NOT raise.
"""
from __future__ import annotations

import pandas as pd
import pytest

from app.agents.schema_understanding_agent import SchemaUnderstandingAgent
from app.agents.execution_planner import ExecutionPlanner
from app.agents.query_verifier import QueryVerifier
from app.agents.pandas_executor_agent import PandasExecutorAgent
from app.schemas.execution_plan import QueryIntent

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def ecommerce_df():
    import numpy as np
    rng = np.random.default_rng(42)
    n = 500
    return pd.DataFrame({
        "order_id":    range(n),
        "product":     rng.choice(["Widget", "Gadget", "Doohickey", "Thingamajig"], n),
        "category":    rng.choice(["Electronics", "Clothing", "Food", "Home"], n),
        "region":      rng.choice(["North", "South", "East", "West"], n),
        "revenue":     rng.uniform(10, 5000, n).round(2),
        "units_sold":  rng.integers(1, 200, n),
        "cost":        rng.uniform(5, 2000, n).round(2),
        "order_date":  pd.date_range("2021-01-01", periods=n, freq="D"),
        "customer_id": rng.integers(1000, 9999, n),
    })


@pytest.fixture(scope="module")
def hr_df():
    import numpy as np
    rng = np.random.default_rng(7)
    n = 300
    return pd.DataFrame({
        "employee_id":  range(n),
        "department":   rng.choice(["Engineering", "Sales", "HR", "Finance"], n),
        "salary":       rng.uniform(30000, 200000, n).round(0),
        "tenure_years": rng.uniform(0.5, 20, n).round(1),
        "performance":  rng.uniform(1, 5, n).round(1),
        "hire_date":    pd.date_range("2010-01-01", periods=n, freq="W"),
        "gender":       rng.choice(["M", "F", "Other"], n),
        "location":     rng.choice(["NYC", "London", "Berlin", "Tokyo"], n),
    })


@pytest.fixture(scope="module")
def health_df():
    import numpy as np
    rng = np.random.default_rng(99)
    n = 400
    return pd.DataFrame({
        "patient_id":  range(n),
        "age":         rng.integers(18, 90, n),
        "bmi":         rng.uniform(15, 45, n).round(1),
        "blood_pressure": rng.uniform(80, 180, n).round(0),
        "cholesterol": rng.uniform(100, 300, n).round(0),
        "diagnosis":   rng.choice(["Healthy", "Diabetes", "Hypertension", "Heart Disease"], n),
        "visits":      rng.integers(1, 20, n),
        "admit_date":  pd.date_range("2020-01-01", periods=n, freq="2D"),
        "hospital":    rng.choice(["City Hospital", "St. Mary's", "General", "Mercy"], n),
    })


@pytest.fixture(scope="module")
def supply_df():
    import numpy as np
    rng = np.random.default_rng(13)
    n = 350
    return pd.DataFrame({
        "sku":            [f"SKU{i:04d}" for i in range(n)],
        "supplier":       rng.choice(["Alpha", "Beta", "Gamma", "Delta"], n),
        "stock_level":    rng.integers(0, 1000, n),
        "lead_time_days": rng.integers(1, 60, n),
        "unit_cost":      rng.uniform(1, 500, n).round(2),
        "defect_rate":    rng.uniform(0, 0.1, n).round(4),
        "reorder_point":  rng.integers(10, 300, n),
        "last_order_date":pd.date_range("2022-01-01", periods=n, freq="D"),
    })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_schema_agent = SchemaUnderstandingAgent()
_planner      = ExecutionPlanner()
_verifier     = QueryVerifier()
_executor     = PandasExecutorAgent()


def _run(df: pd.DataFrame, question: str, expected_intent: QueryIntent | None = None):
    schema = _schema_agent.analyse(df)
    plan   = _planner.build(question, schema)
    plan   = _verifier.verify(plan)
    if plan.is_executable:
        result, code = _executor.execute(df, plan)
        assert result is not None, f"None result for: {question}"
    if expected_intent:
        assert plan.intent == expected_intent, (
            f"Expected {expected_intent}, got {plan.intent} for: {question}"
        )
    return plan


# ---------------------------------------------------------------------------
# E-COMMERCE  (50 questions)
# ---------------------------------------------------------------------------

class TestEcommerce:
    def test_total_revenue(self, ecommerce_df):
        _run(ecommerce_df, "What is the total revenue?", QueryIntent.AGGREGATION)

    def test_average_revenue(self, ecommerce_df):
        _run(ecommerce_df, "What is the average revenue per order?", QueryIntent.AGGREGATION)

    def test_count_orders(self, ecommerce_df):
        _run(ecommerce_df, "How many orders were placed?", QueryIntent.AGGREGATION)

    def test_top_products(self, ecommerce_df):
        _run(ecommerce_df, "Top 10 products by revenue", QueryIntent.RANKING)

    def test_top_categories(self, ecommerce_df):
        _run(ecommerce_df, "Which categories have the highest revenue?", QueryIntent.RANKING)

    def test_lowest_revenue_region(self, ecommerce_df):
        _run(ecommerce_df, "Which region has the lowest revenue?", QueryIntent.RANKING)

    def test_revenue_trend(self, ecommerce_df):
        _run(ecommerce_df, "Show revenue trend over time", QueryIntent.TREND)

    def test_monthly_units(self, ecommerce_df):
        _run(ecommerce_df, "Monthly units sold trend", QueryIntent.TREND)

    def test_revenue_by_category(self, ecommerce_df):
        _run(ecommerce_df, "Revenue breakdown by category", QueryIntent.AGGREGATION)

    def test_revenue_by_region(self, ecommerce_df):
        _run(ecommerce_df, "Total revenue by region", QueryIntent.AGGREGATION)

    def test_compare_regions(self, ecommerce_df):
        _run(ecommerce_df, "Compare revenue across regions", QueryIntent.COMPARISON)

    def test_stats_revenue(self, ecommerce_df):
        _run(ecommerce_df, "Distribution of revenue", QueryIntent.STATISTICS)

    def test_correlation(self, ecommerce_df):
        _run(ecommerce_df, "Correlation between revenue and units sold", QueryIntent.CORRELATION)

    def test_filter_electronics(self, ecommerce_df):
        _run(ecommerce_df, "Show only Electronics orders", QueryIntent.FILTERING)

    def test_summarize(self, ecommerce_df):
        _run(ecommerce_df, "Summarize this dataset", QueryIntent.SUMMARIZATION)

    def test_anomaly(self, ecommerce_df):
        _run(ecommerce_df, "Are there any revenue outliers?", QueryIntent.ANOMALY)

    def test_recommend(self, ecommerce_df):
        _run(ecommerce_df, "What should we do to increase revenue?", QueryIntent.RECOMMENDATION)

    def test_optimize(self, ecommerce_df):
        _run(ecommerce_df, "Optimize cost to maximize profit", QueryIntent.OPTIMIZATION)

    def test_root_cause(self, ecommerce_df):
        _run(ecommerce_df, "Why is revenue low in some regions?", QueryIntent.ROOT_CAUSE)

    def test_forecast_no_date(self, ecommerce_df):
        # forecasting with dates present — should be executable
        plan = _run(ecommerce_df, "Forecast revenue for next month")
        # Plan may be unsupported (forecasting not yet implemented) but must not raise

    def test_max_units(self, ecommerce_df):
        _run(ecommerce_df, "What is the maximum units sold in a single order?", QueryIntent.AGGREGATION)

    def test_min_cost(self, ecommerce_df):
        _run(ecommerce_df, "Minimum cost order", QueryIntent.AGGREGATION)

    def test_top5_by_units(self, ecommerce_df):
        _run(ecommerce_df, "Top 5 products by units sold", QueryIntent.RANKING)

    def test_revenue_2022(self, ecommerce_df):
        _run(ecommerce_df, "Total revenue in 2022", QueryIntent.AGGREGATION)

    def test_quarterly_trend(self, ecommerce_df):
        _run(ecommerce_df, "Quarterly revenue trend", QueryIntent.TREND)

    def test_std_revenue(self, ecommerce_df):
        _run(ecommerce_df, "Standard deviation of revenue", QueryIntent.STATISTICS)

    def test_median_revenue(self, ecommerce_df):
        _run(ecommerce_df, "Median order revenue", QueryIntent.STATISTICS)

    def test_category_comparison(self, ecommerce_df):
        _run(ecommerce_df, "Compare Electronics vs Clothing revenue", QueryIntent.COMPARISON)

    def test_product_count(self, ecommerce_df):
        _run(ecommerce_df, "How many distinct products are there?", QueryIntent.AGGREGATION)

    def test_top_regions_units(self, ecommerce_df):
        _run(ecommerce_df, "Which region sells the most units?", QueryIntent.RANKING)

    def test_revenue_histogram(self, ecommerce_df):
        _run(ecommerce_df, "Show histogram of revenue", QueryIntent.STATISTICS)

    def test_cost_revenue_scatter(self, ecommerce_df):
        _run(ecommerce_df, "Scatter plot of cost vs revenue", QueryIntent.VISUALIZATION)

    def test_yearly_growth(self, ecommerce_df):
        _run(ecommerce_df, "What is the year-over-year revenue growth?", QueryIntent.TREND)

    def test_bottom5_products(self, ecommerce_df):
        _run(ecommerce_df, "Bottom 5 products by revenue", QueryIntent.RANKING)

    def test_total_units(self, ecommerce_df):
        _run(ecommerce_df, "Total units sold across all products", QueryIntent.AGGREGATION)

    def test_avg_cost_by_category(self, ecommerce_df):
        _run(ecommerce_df, "Average cost by category", QueryIntent.AGGREGATION)

    def test_high_revenue_filter(self, ecommerce_df):
        _run(ecommerce_df, "Show orders where revenue > 1000", QueryIntent.FILTERING)

    def test_describe_dataset(self, ecommerce_df):
        _run(ecommerce_df, "What is the summary statistics of the dataset?", QueryIntent.STATISTICS)

    def test_north_region(self, ecommerce_df):
        _run(ecommerce_df, "Filter orders from North region", QueryIntent.FILTERING)

    def test_product_revenue_pie(self, ecommerce_df):
        _run(ecommerce_df, "Pie chart of revenue by product", QueryIntent.VISUALIZATION)

    def test_correlation_matrix(self, ecommerce_df):
        _run(ecommerce_df, "Show correlation matrix", QueryIntent.CORRELATION)

    def test_daily_revenue(self, ecommerce_df):
        _run(ecommerce_df, "Daily revenue trend", QueryIntent.TREND)

    def test_rank_by_cost(self, ecommerce_df):
        _run(ecommerce_df, "Rank categories by cost", QueryIntent.RANKING)

    def test_revenue_variance(self, ecommerce_df):
        _run(ecommerce_df, "Variance in revenue", QueryIntent.STATISTICS)

    def test_units_per_region(self, ecommerce_df):
        _run(ecommerce_df, "Average units sold per region", QueryIntent.AGGREGATION)

    def test_total_cost(self, ecommerce_df):
        _run(ecommerce_df, "What is the total cost?", QueryIntent.AGGREGATION)

    def test_orders_per_day(self, ecommerce_df):
        _run(ecommerce_df, "How many orders per day?", QueryIntent.TREND)

    def test_category_count(self, ecommerce_df):
        _run(ecommerce_df, "Number of orders per category", QueryIntent.AGGREGATION)

    def test_top_customer(self, ecommerce_df):
        _run(ecommerce_df, "Who are the top 5 customers by revenue?", QueryIntent.RANKING)

    def test_low_cost_orders(self, ecommerce_df):
        _run(ecommerce_df, "List orders with cost less than 100", QueryIntent.FILTERING)


# ---------------------------------------------------------------------------
# HR  (35 questions)
# ---------------------------------------------------------------------------

class TestHR:
    def test_avg_salary(self, hr_df):
        _run(hr_df, "What is the average salary?", QueryIntent.AGGREGATION)

    def test_top_paid_dept(self, hr_df):
        _run(hr_df, "Which department has the highest average salary?", QueryIntent.RANKING)

    def test_salary_by_dept(self, hr_df):
        _run(hr_df, "Total salary cost by department", QueryIntent.AGGREGATION)

    def test_tenure_distribution(self, hr_df):
        _run(hr_df, "Distribution of employee tenure", QueryIntent.STATISTICS)

    def test_performance_trend(self, hr_df):
        _run(hr_df, "How has average performance changed over time?", QueryIntent.TREND)

    def test_salary_gender(self, hr_df):
        _run(hr_df, "Compare average salary by gender", QueryIntent.COMPARISON)

    def test_high_performers(self, hr_df):
        _run(hr_df, "Show employees with performance above 4", QueryIntent.FILTERING)

    def test_salary_performance_corr(self, hr_df):
        _run(hr_df, "Correlation between salary and performance", QueryIntent.CORRELATION)

    def test_headcount_dept(self, hr_df):
        _run(hr_df, "How many employees per department?", QueryIntent.AGGREGATION)

    def test_salary_outliers(self, hr_df):
        _run(hr_df, "Are there any salary outliers?", QueryIntent.ANOMALY)

    def test_retention_reco(self, hr_df):
        _run(hr_df, "Recommend actions to improve retention", QueryIntent.RECOMMENDATION)

    def test_top10_salary(self, hr_df):
        _run(hr_df, "Top 10 highest paid employees", QueryIntent.RANKING)

    def test_salary_stats(self, hr_df):
        _run(hr_df, "Salary statistics by department", QueryIntent.STATISTICS)

    def test_location_headcount(self, hr_df):
        _run(hr_df, "Headcount by location", QueryIntent.AGGREGATION)

    def test_hiring_trend(self, hr_df):
        _run(hr_df, "Hiring trend over the years", QueryIntent.TREND)

    def test_median_salary(self, hr_df):
        _run(hr_df, "Median salary across all employees", QueryIntent.STATISTICS)

    def test_low_performers(self, hr_df):
        _run(hr_df, "List employees with performance below 2", QueryIntent.FILTERING)

    def test_salary_tenure_corr(self, hr_df):
        _run(hr_df, "Does tenure affect salary?", QueryIntent.CORRELATION)

    def test_max_salary(self, hr_df):
        _run(hr_df, "What is the maximum salary?", QueryIntent.AGGREGATION)

    def test_dept_vs_dept(self, hr_df):
        _run(hr_df, "Compare Engineering vs Sales salary", QueryIntent.COMPARISON)

    def test_gender_count(self, hr_df):
        _run(hr_df, "Count employees by gender", QueryIntent.AGGREGATION)

    def test_root_cause_low_perf(self, hr_df):
        _run(hr_df, "Why are some departments underperforming?", QueryIntent.ROOT_CAUSE)

    def test_optimize_team_size(self, hr_df):
        _run(hr_df, "Optimize team size to minimize salary cost", QueryIntent.OPTIMIZATION)

    def test_salary_histogram(self, hr_df):
        _run(hr_df, "Histogram of salaries", QueryIntent.STATISTICS)

    def test_tenure_salary_scatter(self, hr_df):
        _run(hr_df, "Scatter plot of tenure vs salary", QueryIntent.VISUALIZATION)

    def test_new_hires_monthly(self, hr_df):
        _run(hr_df, "Monthly new hires trend", QueryIntent.TREND)

    def test_top5_performers(self, hr_df):
        _run(hr_df, "Top 5 employees by performance", QueryIntent.RANKING)

    def test_finance_dept(self, hr_df):
        _run(hr_df, "Show Finance department employees", QueryIntent.FILTERING)

    def test_salary_by_location(self, hr_df):
        _run(hr_df, "Average salary by location", QueryIntent.AGGREGATION)

    def test_variance_salary(self, hr_df):
        _run(hr_df, "Variance in salary by department", QueryIntent.STATISTICS)

    def test_total_payroll(self, hr_df):
        _run(hr_df, "Total payroll cost", QueryIntent.AGGREGATION)

    def test_performance_by_gender(self, hr_df):
        _run(hr_df, "Average performance score by gender", QueryIntent.AGGREGATION)

    def test_headcount_over_time(self, hr_df):
        _run(hr_df, "How has headcount grown over time?", QueryIntent.TREND)

    def test_dept_performance_rank(self, hr_df):
        _run(hr_df, "Rank departments by average performance", QueryIntent.RANKING)

    def test_summarize_hr(self, hr_df):
        _run(hr_df, "Give me an overview of this HR dataset", QueryIntent.SUMMARIZATION)


# ---------------------------------------------------------------------------
# Health  (35 questions)
# ---------------------------------------------------------------------------

class TestHealth:
    def test_avg_bmi(self, health_df):
        _run(health_df, "What is the average BMI?", QueryIntent.AGGREGATION)

    def test_patient_count(self, health_df):
        _run(health_df, "How many patients are there?", QueryIntent.AGGREGATION)

    def test_diagnosis_distribution(self, health_df):
        _run(health_df, "Distribution of diagnoses", QueryIntent.STATISTICS)

    def test_top_hospitals(self, health_df):
        _run(health_df, "Which hospitals have the most patients?", QueryIntent.RANKING)

    def test_age_bmi_corr(self, health_df):
        _run(health_df, "Correlation between age and BMI", QueryIntent.CORRELATION)

    def test_avg_age_by_diagnosis(self, health_df):
        _run(health_df, "Average age by diagnosis", QueryIntent.AGGREGATION)

    def test_high_bp_filter(self, health_df):
        _run(health_df, "Show patients with blood pressure above 140", QueryIntent.FILTERING)

    def test_admission_trend(self, health_df):
        _run(health_df, "Monthly patient admissions trend", QueryIntent.TREND)

    def test_visits_stats(self, health_df):
        _run(health_df, "Statistics on number of visits", QueryIntent.STATISTICS)

    def test_bmi_outliers(self, health_df):
        _run(health_df, "Detect BMI outliers", QueryIntent.ANOMALY)

    def test_heart_disease_count(self, health_df):
        _run(health_df, "How many heart disease patients?", QueryIntent.AGGREGATION)

    def test_compare_hospitals(self, health_df):
        _run(health_df, "Compare average BMI across hospitals", QueryIntent.COMPARISON)

    def test_cholesterol_bmi_corr(self, health_df):
        _run(health_df, "Does cholesterol correlate with BMI?", QueryIntent.CORRELATION)

    def test_diagnosis_by_hospital(self, health_df):
        _run(health_df, "Patient count by hospital and diagnosis", QueryIntent.AGGREGATION)

    def test_recommend_health(self, health_df):
        _run(health_df, "Recommend interventions for high-risk patients", QueryIntent.RECOMMENDATION)

    def test_elderly_filter(self, health_df):
        _run(health_df, "Filter patients older than 65", QueryIntent.FILTERING)

    def test_top_diagnoses(self, health_df):
        _run(health_df, "Top 3 most common diagnoses", QueryIntent.RANKING)

    def test_yearly_admissions(self, health_df):
        _run(health_df, "Yearly patient admissions trend", QueryIntent.TREND)

    def test_avg_cholesterol(self, health_df):
        _run(health_df, "Average cholesterol level", QueryIntent.AGGREGATION)

    def test_bp_distribution(self, health_df):
        _run(health_df, "Blood pressure distribution", QueryIntent.STATISTICS)

    def test_visits_by_diagnosis(self, health_df):
        _run(health_df, "Average visits per diagnosis", QueryIntent.AGGREGATION)

    def test_max_bp(self, health_df):
        _run(health_df, "Maximum blood pressure recorded", QueryIntent.AGGREGATION)

    def test_summarize_health(self, health_df):
        _run(health_df, "Summarize this health dataset", QueryIntent.SUMMARIZATION)

    def test_correlation_matrix(self, health_df):
        _run(health_df, "Show correlation matrix of all numeric columns", QueryIntent.CORRELATION)

    def test_hypertension_filter(self, health_df):
        _run(health_df, "List all hypertension patients", QueryIntent.FILTERING)

    def test_bmi_histogram(self, health_df):
        _run(health_df, "Histogram of BMI values", QueryIntent.STATISTICS)

    def test_age_distribution(self, health_df):
        _run(health_df, "Age distribution of patients", QueryIntent.STATISTICS)

    def test_root_cause_readmission(self, health_df):
        _run(health_df, "Why do some patients have more visits?", QueryIntent.ROOT_CAUSE)

    def test_age_visits_corr(self, health_df):
        _run(health_df, "Does age affect number of visits?", QueryIntent.CORRELATION)

    def test_hospital_rank(self, health_df):
        _run(health_df, "Rank hospitals by average patient age", QueryIntent.RANKING)

    def test_diabetes_avg_bmi(self, health_df):
        _run(health_df, "Average BMI for diabetes patients", QueryIntent.AGGREGATION)

    def test_young_patients(self, health_df):
        _run(health_df, "Patients under 30 years old", QueryIntent.FILTERING)

    def test_total_visits(self, health_df):
        _run(health_df, "Total visits across all patients", QueryIntent.AGGREGATION)

    def test_bp_cholesterol_scatter(self, health_df):
        _run(health_df, "Scatter plot of blood pressure vs cholesterol", QueryIntent.VISUALIZATION)

    def test_monthly_diagnosis_trend(self, health_df):
        _run(health_df, "Monthly trend of Heart Disease diagnoses", QueryIntent.TREND)


# ---------------------------------------------------------------------------
# Supply Chain  (30 questions)
# ---------------------------------------------------------------------------

class TestSupplyChain:
    def test_avg_lead_time(self, supply_df):
        _run(supply_df, "Average lead time by supplier", QueryIntent.AGGREGATION)

    def test_top_defect_suppliers(self, supply_df):
        _run(supply_df, "Which suppliers have the highest defect rates?", QueryIntent.RANKING)

    def test_total_stock(self, supply_df):
        _run(supply_df, "Total stock level across all SKUs", QueryIntent.AGGREGATION)

    def test_low_stock_filter(self, supply_df):
        _run(supply_df, "Show items where stock level < 50", QueryIntent.FILTERING)

    def test_cost_by_supplier(self, supply_df):
        _run(supply_df, "Average unit cost by supplier", QueryIntent.AGGREGATION)

    def test_defect_cost_corr(self, supply_df):
        _run(supply_df, "Correlation between defect rate and unit cost", QueryIntent.CORRELATION)

    def test_reorder_stats(self, supply_df):
        _run(supply_df, "Statistics on reorder points", QueryIntent.STATISTICS)

    def test_ordering_trend(self, supply_df):
        _run(supply_df, "Order frequency trend over time", QueryIntent.TREND)

    def test_high_cost_items(self, supply_df):
        _run(supply_df, "Top 10 most expensive items", QueryIntent.RANKING)

    def test_optimize_procurement(self, supply_df):
        _run(supply_df, "Recommend optimal procurement strategy", QueryIntent.RECOMMENDATION)

    def test_supplier_count(self, supply_df):
        _run(supply_df, "How many SKUs per supplier?", QueryIntent.AGGREGATION)

    def test_anomaly_defects(self, supply_df):
        _run(supply_df, "Detect anomalies in defect rates", QueryIntent.ANOMALY)

    def test_lead_time_distribution(self, supply_df):
        _run(supply_df, "Distribution of lead times", QueryIntent.STATISTICS)

    def test_compare_suppliers(self, supply_df):
        _run(supply_df, "Compare Alpha vs Beta supplier performance", QueryIntent.COMPARISON)

    def test_root_cause_delays(self, supply_df):
        _run(supply_df, "Why are some lead times so long?", QueryIntent.ROOT_CAUSE)

    def test_monthly_orders(self, supply_df):
        _run(supply_df, "Monthly order volume trend", QueryIntent.TREND)

    def test_min_stock(self, supply_df):
        _run(supply_df, "Which SKU has the minimum stock level?", QueryIntent.RANKING)

    def test_max_defect_rate(self, supply_df):
        _run(supply_df, "Maximum defect rate recorded", QueryIntent.AGGREGATION)

    def test_cost_stats(self, supply_df):
        _run(supply_df, "Summary statistics of unit cost", QueryIntent.STATISTICS)

    def test_reorder_needed(self, supply_df):
        _run(supply_df, "Items where stock is below reorder point", QueryIntent.FILTERING)

    def test_total_cost(self, supply_df):
        _run(supply_df, "Total procurement cost", QueryIntent.AGGREGATION)

    def test_lead_time_cost_corr(self, supply_df):
        _run(supply_df, "Does lead time correlate with cost?", QueryIntent.CORRELATION)

    def test_rank_by_stock(self, supply_df):
        _run(supply_df, "Rank suppliers by total stock", QueryIntent.RANKING)

    def test_optimize_cost(self, supply_df):
        _run(supply_df, "Minimize total procurement cost", QueryIntent.OPTIMIZATION)

    def test_summarize_supply(self, supply_df):
        _run(supply_df, "Summarize the supply chain dataset", QueryIntent.SUMMARIZATION)

    def test_gamma_supplier(self, supply_df):
        _run(supply_df, "Show all Gamma supplier items", QueryIntent.FILTERING)

    def test_cost_histogram(self, supply_df):
        _run(supply_df, "Histogram of unit costs", QueryIntent.STATISTICS)

    def test_defect_trend(self, supply_df):
        _run(supply_df, "Trend in defect rates over time", QueryIntent.TREND)

    def test_avg_defect_by_supplier(self, supply_df):
        _run(supply_df, "Average defect rate per supplier", QueryIntent.AGGREGATION)

    def test_visualize_lead_times(self, supply_df):
        _run(supply_df, "Visualize lead time distribution", QueryIntent.VISUALIZATION)
