from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
from dotenv import load_dotenv
from google import genai
import os
import re
import sqlite3
import time
import math

# ==========================================
# CONFIGURATION
# ==========================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

DB_PATH = os.path.join(BASE_DIR, "sales.db")
MODEL_NAME = "gemini-2.5-flash"

api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key) if api_key else None

app = FastAPI(
    title="InsightAI - AI Data Analyst",
    description="Analyze CSV datasets using natural language and AI.",
    version="1.8.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

dataset = None


# ==========================================
# GENERAL HELPERS
# ==========================================

def get_column_name(columns, *candidates):
    lookup = {
        str(column).strip().lower(): column
        for column in columns
    }

    for candidate in candidates:
        if candidate.lower() in lookup:
            return lookup[candidate.lower()]

    return None


def safe_number(value):
    if value is None or pd.isna(value):
        return None

    number = float(value)

    if not math.isfinite(number):
        return None

    return int(number) if number.is_integer() else round(number, 2)


def json_safe_value(value):
    if value is None or pd.isna(value):
        return None

    if hasattr(value, "item"):
        value = value.item()

    if isinstance(value, float) and not math.isfinite(value):
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    return str(value)


def load_saved_dataset():
    global dataset

    if dataset is not None:
        return dataset

    if not os.path.exists(DB_PATH):
        return None

    try:
        conn = sqlite3.connect(DB_PATH)

        try:
            dataset = pd.read_sql_query(
                "SELECT * FROM sales", conn
            )
        finally:
            conn.close()

        return dataset

    except Exception as e:
        print("Could not load saved dataset:", str(e))
        return None


# ==========================================
# DATASET STATISTICS
# ==========================================

def calculate_dataset_statistics(df):
    numeric_statistics = {}
    categorical_statistics = {}

    for column in df.columns:
        series = df[column]
        numeric_series = pd.to_numeric(series, errors="coerce")
        non_empty = series.notna()

        is_numeric = (
            non_empty.any()
            and numeric_series[non_empty].notna().all()
        )

        if is_numeric:
            values = numeric_series.dropna()

            numeric_statistics[str(column)] = {
                "count": int(values.count()),
                "sum": safe_number(values.sum()),
                "average": safe_number(values.mean()),
                "minimum": safe_number(values.min()),
                "maximum": safe_number(values.max()),
            }
        else:
            categorical_statistics[str(column)] = {
                "unique_values": int(series.nunique(dropna=True)),
                "missing_values": int(series.isna().sum()),
            }

    return {
        "total_records": int(len(df)),
        "total_columns": int(len(df.columns)),
        "numeric_statistics": numeric_statistics,
        "categorical_statistics": categorical_statistics,
    }


# ==========================================
# QUESTION VALIDATION
# ==========================================

def find_unsupported_fields(question, columns):
    question_words = set(
        re.findall(r"[a-zA-Z_]+", question.lower())
    )

    normalized_columns = {
        re.sub(r"[^a-z0-9]", "", str(column).lower())
        for column in columns
    }

    concepts = {
        "salary": {
            "terms": {
                "salary", "salaries", "pay", "wage", "wages",
                "compensation", "payroll",
            },
            "columns": {
                "salary", "salaries", "pay", "wage", "wages",
                "compensation", "payroll", "basesalary",
                "totalsalary", "annualsalary",
            },
        },
        "employee": {
            "terms": {
                "employee", "employees", "staff", "worker",
                "workers", "personnel",
            },
            "columns": {
                "employee", "employees", "employeeid",
                "employeename", "staff", "staffid",
                "staffname", "worker", "workerid",
                "workername", "personnel",
            },
        },
        "age": {
            "terms": {"age", "ages"},
            "columns": {"age", "ages", "employeeage"},
        },
        "department": {
            "terms": {"department", "departments"},
            "columns": {
                "department", "departments",
                "departmentid", "departmentname",
            },
        },
        "address": {
            "terms": {"address", "addresses"},
            "columns": {"address", "addresses", "location"},
        },
    }

    missing = []

    for concept, definition in concepts.items():
        if question_words.intersection(definition["terms"]):
            available = any(
                column in normalized_columns
                for column in definition["columns"]
            )

            if concept == "address":
                available = any(
                    column in normalized_columns
                    for column in {"address", "addresses"}
                )

            if not available:
                missing.append(concept)

    return missing


def unsupported_question_response(question, columns, missing_fields):
    field_text = ", ".join(missing_fields)
    column_text = ", ".join(str(column) for column in columns)

    answer = (
        f"I can't answer this question because your dataset "
        f"doesn't contain information for: {field_text}. "
        f"Available columns are: {column_text}."
    )

    return {
        "question": question,
        "answer": answer,
        "error": "The requested information is not available in this dataset.",
        "details": f"Missing information: {field_text}",
        "sql": None,
        "result": [],
        "chart": None,
    } 
# ==========================================
# CHART GENERATION
# ==========================================

def normalize_name(value):
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def build_chart(result, question):
    """Build a chart and choose a suitable chart type automatically."""
    if result is None or result.empty or len(result.columns) < 2:
        return None

    question_lower = str(question).lower()
    columns = list(result.columns)

    numeric_columns = []
    for column in columns:
        converted = pd.to_numeric(result[column], errors="coerce")
        if converted.notna().any() and converted.notna().all():
            numeric_columns.append(column)

    if not numeric_columns:
        return None

    category_columns = [
        column for column in columns
        if column not in numeric_columns
    ]
    if not category_columns:
        return None

    preferred_metrics = [
        "total_revenue", "average_revenue", "revenue", "sales_amount",
        "total_sales", "sales", "average_order_value", "total_profit",
        "profit", "average_marks", "marks", "average_score", "score",
        "total_quantity", "units_sold", "quantity", "average_price",
        "price", "average", "avg", "sum", "count", "total",
    ]

    def metric_score(column):
        name = normalize_name(column)
        score = 0
        for index, metric in enumerate(preferred_metrics):
            normalized_metric = normalize_name(metric)
            if name == normalized_metric:
                score = max(score, 1000 - index)
            elif normalized_metric in name:
                score = max(score, 500 - index)
        if name.endswith("id") or name == "id":
            score -= 1000
        return score

    y_column = max(numeric_columns, key=metric_score)
    if metric_score(y_column) <= 0:
        y_column = numeric_columns[-1]

    # Prefer the category mentioned in the user's question.
    x_column = None
    normalized_question = normalize_name(question_lower)
    for column in category_columns:
        column_name = str(column).lower().replace("_", " ")
        normalized_column = normalize_name(column)
        if column_name in question_lower or (
            normalized_column and normalized_column in normalized_question
        ):
            x_column = column
            break

    # Prefer dates for trend questions.
    trend_words = (
        "trend", "over time", "by date", "by month", "by year",
        "daily", "monthly", "yearly", "timeline", "time series",
    )
    asks_for_trend = any(word in question_lower for word in trend_words)

    date_column = None
    for column in category_columns:
        name = normalize_name(column)
        looks_like_date_name = any(
            word in name for word in ("date", "month", "year", "time", "timestamp")
        )
        parsed_dates = pd.to_datetime(result[column], errors="coerce")

        if looks_like_date_name and parsed_dates.notna().all():
            date_column = column
            break

        if len(result[column]) > 0 and parsed_dates.notna().all():
            original_strings = result[column].astype(str)
            if original_strings.str.contains(r"[-/:]", regex=True).all():
                date_column = column
                break

    if asks_for_trend and date_column is not None:
        x_column = date_column
    elif x_column is None:
        x_column = date_column or category_columns[0]

    chart_rows = result[[x_column, y_column]].copy()
    chart_rows[y_column] = pd.to_numeric(
        chart_rows[y_column], errors="coerce"
    )
    chart_rows = chart_rows.dropna(subset=[x_column, y_column])

    if chart_rows.empty:
        return None

    if x_column == date_column:
        chart_rows["__chart_date_sort"] = pd.to_datetime(
            chart_rows[x_column], errors="coerce"
        )
        chart_rows = chart_rows.sort_values("__chart_date_sort").drop(
            columns=["__chart_date_sort"]
        )

    chart_data = []
    for _, row in chart_rows.iterrows():
        category_value = json_safe_value(row[x_column])
        metric_value = safe_number(row[y_column])

        if category_value is None or metric_value is None:
            continue

        chart_data.append({
            str(x_column): category_value,
            str(y_column): metric_value,
        })

    if not chart_data:
        return None

    pie_words = (
        "share", "proportion", "percentage", "percent", "distribution",
        "breakdown", "composition", "contribution",
    )
    asks_for_pie = any(word in question_lower for word in pie_words)

    if x_column == date_column and asks_for_trend:
        chart_type = "line"
    elif asks_for_pie and 2 <= len(chart_data) <= 7:
        chart_type = "pie"
    else:
        chart_type = "bar"

    readable_metric = str(y_column).replace("_", " ").title()
    readable_category = str(x_column).replace("_", " ").title()

    return {
        "type": chart_type,
        "title": f"{readable_metric} by {readable_category}",
        "x_key": str(x_column),
        "y_key": str(y_column),
        "data": chart_data,
    }


# ==========================================
# HOME
# ==========================================

@app.get("/")
def home():
    return {"message": "InsightAI API is running!"}


# ==========================================
# UPLOAD CSV
# ==========================================

@app.post("/upload")
async def upload_csv(file: UploadFile = File(...)):
    global dataset

    try:
        if not file.filename or not file.filename.lower().endswith(".csv"):
            return {"error": "Please upload a CSV file."}

        uploaded_dataset = pd.read_csv(file.file)

        if uploaded_dataset.empty:
            return {"error": "The uploaded CSV file is empty."}

        if len(uploaded_dataset.columns) == 0:
            return {"error": "The CSV file has no columns."}

        if not uploaded_dataset.columns.is_unique:
            return {"error": "The CSV contains duplicate column names."}

        conn = sqlite3.connect(DB_PATH)

        try:
            uploaded_dataset.to_sql(
                "sales",
                conn,
                if_exists="replace",
                index=False,
            )
        finally:
            conn.close()

        dataset = uploaded_dataset

        return {
            "message": "Dataset uploaded successfully",
            "filename": file.filename,
            "rows": len(dataset),
            "columns": list(dataset.columns),
        }

    except Exception as e:
        print("Upload failed:", str(e))
        return {
            "error": "Failed to upload dataset",
            "details": str(e),
        }

    finally:
        await file.close()


# ==========================================
# DATASET INFORMATION
# ==========================================

@app.get("/dataset")
def get_dataset_info():
    current_dataset = load_saved_dataset()

    if current_dataset is None:
        return {"message": "No dataset uploaded yet"}

    return {
        "rows": len(current_dataset),
        "columns": list(current_dataset.columns),
        "data_types": current_dataset.dtypes.astype(str).to_dict(),
        "statistics": calculate_dataset_statistics(current_dataset),
    }


# ==========================================
# DASHBOARD STATISTICS
# ==========================================

@app.get("/dashboard-stats")
def get_dashboard_stats():
    current_dataset = load_saved_dataset()

    if current_dataset is None:
        return {
            "dataset_loaded": False,
            "message": "Upload a CSV dataset to view dashboard statistics.",
            "rows": 0,
            "columns": [],
            "total_revenue": None,
            "total_orders": None,
            "units_sold": None,
            "average_order_value": None,
            "statistics": None,
        }

    columns = current_dataset.columns

    revenue_col = get_column_name(
        columns, "revenue", "total_revenue", "sales_amount"
    )
    order_col = get_column_name(
        columns, "order_id", "orderid", "order_number"
    )
    quantity_col = get_column_name(
        columns, "quantity", "qty", "units_sold"
    )
    price_col = get_column_name(columns, "price", "unit_price")

    total_revenue = None

    if revenue_col is not None:
        values = pd.to_numeric(
            current_dataset[revenue_col], errors="coerce"
        )
        if values.notna().any():
            total_revenue = safe_number(values.sum())

    elif price_col is not None and quantity_col is not None:
        prices = pd.to_numeric(
            current_dataset[price_col], errors="coerce"
        )
        quantities = pd.to_numeric(
            current_dataset[quantity_col], errors="coerce"
        )
        valid = prices.notna() & quantities.notna()

        if valid.any():
            total_revenue = safe_number(
                (prices[valid] * quantities[valid]).sum()
            )

    total_orders = (
        int(current_dataset[order_col].nunique(dropna=True))
        if order_col is not None
        else int(len(current_dataset))
    )

    units_sold = None

    if quantity_col is not None:
        quantities = pd.to_numeric(
            current_dataset[quantity_col], errors="coerce"
        )
        if quantities.notna().any():
            units_sold = safe_number(quantities.sum())

    average_order_value = None

    if total_revenue is not None and total_orders > 0:
        average_order_value = safe_number(
            total_revenue / total_orders
        )

    statistics = calculate_dataset_statistics(current_dataset)

    return {
        "dataset_loaded": True,
        "rows": int(len(current_dataset)),
        "columns": list(current_dataset.columns),
        "total_revenue": total_revenue,
        "total_orders": total_orders,
        "units_sold": units_sold,
        "average_order_value": average_order_value,
        "statistics": statistics,
    } 

# ==========================================
# GEMINI REQUEST WITH QUOTA HANDLING
# ==========================================

def generate_gemini_response(prompt):
    if client is None:
        raise RuntimeError(
            "GEMINI_API_KEY is missing. Check backend/.env."
        )

    for attempt in range(3):
        try:
            print(
                f"Calling {MODEL_NAME} "
                f"(attempt {attempt + 1}/3)..."
            )

            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
            )

            if not response.text:
                raise RuntimeError(
                    "Gemini returned an empty response."
                )

            return response

        except Exception as e:
            message = str(e).upper()

            quota_exhausted = (
                "RESOURCE_EXHAUSTED" in message
                or "QUOTA EXCEEDED" in message
                or (
                    "429" in message
                    and (
                        "FREE_TIER" in message
                        or "QUOTA" in message
                    )
                )
            )

            if quota_exhausted:
                raise RuntimeError(
                    "GEMINI_QUOTA_EXHAUSTED: Your Gemini API "
                    "quota has been reached. Please wait for "
                    "the quota to reset or check your usage at "
                    "https://ai.dev/rate-limit. You can continue "
                    "testing uploads, dashboard statistics, and "
                    "charts without Gemini."
                ) from e

            temporary_error = any(
                marker in message
                for marker in (
                    "503", "UNAVAILABLE", "500", "INTERNAL"
                )
            )

            if temporary_error and attempt < 2:
                wait_time = 2 ** (attempt + 1)

                print(
                    f"Temporary Gemini server error. "
                    f"Retrying in {wait_time}s..."
                )

                time.sleep(wait_time)
            else:
                raise


# ==========================================
# ASK QUESTION
# ==========================================

@app.post("/ask")
async def ask_question(question: str):
    current_dataset = load_saved_dataset()

    if current_dataset is None:
        return {"error": "Please upload a dataset first."}

    if not question.strip():
        return {"error": "Please enter a question."}

    columns = list(current_dataset.columns)
    missing_fields = find_unsupported_fields(question, columns)

    if missing_fields:
        print("Question rejected: missing dataset fields", missing_fields)

        return unsupported_question_response(
            question, columns, missing_fields
        )

    if client is None:
        return {
            "error": "Gemini API key is missing. Check backend/.env."
        }

    schema = {
        "columns": columns,
        "data_types": current_dataset.dtypes.astype(str).to_dict(),
        "rows": len(current_dataset),
    }

    sql_prompt = f"""
You are an AI Data Analyst.

SQLite table name: sales

Dataset schema:
{schema}

User question:
{question}

Generate exactly one SQLite SELECT query that answers the question.

Rules:
- Use only the sales table.
- Use only actual columns in the provided schema.
- Never invent a column or pretend a calculated alias is real data.
- If the question asks for information the schema cannot support,
  return exactly: UNSUPPORTED_QUESTION
- For a numeric metric grouped by a category, return the category
  first and the numeric metric second.
- Use clear aliases such as total_revenue or average_marks.
- For revenue by region, group by region and calculate SUM(revenue)
  when those columns exist.
- Return only SQL or UNSUPPORTED_QUESTION.
- Do not include markdown or explanations.
- Never generate INSERT, UPDATE, DELETE, DROP, ALTER, CREATE,
  PRAGMA, ATTACH, or other non-SELECT statements.
"""

    try:
        sql_response = generate_gemini_response(sql_prompt)
        sql_query = sql_response.text.strip()

        sql_query = re.sub(
            r"^```(?:sql|sqlite|sqlite3)?\s*",
            "",
            sql_query,
            flags=re.IGNORECASE,
        )
        sql_query = re.sub(r"\s*```$", "", sql_query).strip()

    except Exception as e:
        error_message = str(e)
        print("Gemini SQL generation failed:", error_message)

        if "GEMINI_QUOTA_EXHAUSTED" in error_message:
            return {
                "question": question,
                "error": (
                    "Gemini's API quota has been reached. "
                    "Please wait for it to reset or check your "
                    "usage at https://ai.dev/rate-limit. "
                    "Uploads, dashboard statistics, and chart "
                    "testing can continue without Gemini."
                ),
                "details": error_message,
            }

        return {
            "question": question,
            "error": "Failed to generate SQL with Gemini.",
            "details": error_message,
        }

    if sql_query.strip().upper() == "UNSUPPORTED_QUESTION":
        return unsupported_question_response(
            question,
            columns,
            ["the information requested in your question"],
        )

    normalized_sql = sql_query.rstrip().rstrip(";").strip()
    sql_upper = normalized_sql.upper()

    if not re.match(r"^SELECT\b", sql_upper):
        return {
            "question": question,
            "sql": sql_query,
            "error": "Only SELECT queries are allowed.",
        }

    if ";" in normalized_sql:
        return {
            "question": question,
            "sql": sql_query,
            "error": "Multiple SQL statements are not allowed.",
        }

    if any(marker in normalized_sql for marker in ("--", "/*", "*/")):
        return {
            "question": question,
            "sql": sql_query,
            "error": "SQL comments are not allowed.",
        }

    try:
        conn = sqlite3.connect(DB_PATH)

        try:
            conn.execute("PRAGMA query_only = ON")
            conn.execute("EXPLAIN " + normalized_sql)
            result = pd.read_sql_query(normalized_sql, conn)
        finally:
            conn.close()

    except Exception as e:
        print("SQL validation or execution failed:", str(e))

        return {
            "question": question,
            "sql": normalized_sql,
            "error": "The generated SQL could not be executed safely.",
            "details": str(e),
        }

    result_data = [
        {
            str(key): json_safe_value(value)
            for key, value in row.items()
        }
        for row in result.to_dict(orient="records")
    ]

    chart = build_chart(result, question)

    if result.empty:
        answer = "No results were found for your question."

    else:
        explanation_prompt = f"""
You are an AI Data Analyst.

User question:
{question}

Actual SQL result:
{result.to_string(index=False)}

Answer using only the actual SQL result.
Do not invent columns, values, salaries, or facts.
If the result does not contain the information needed to answer
the question, clearly state that the dataset does not provide it.
Keep the answer within 2-3 sentences.
"""

        try:
            explanation_response = generate_gemini_response(
                explanation_prompt
            )
            answer = explanation_response.text.strip()

        except Exception as e:
            error_message = str(e)
            print("AI explanation generation failed:", error_message)

            if "GEMINI_QUOTA_EXHAUSTED" in error_message:
                answer = (
                    "The SQL analysis completed successfully, but "
                    "Gemini's quota has been reached, so an AI "
                    "explanation could not be generated. "
                    "The actual query results are shown below."
                )
            else:
                answer = (
                    "Analysis completed. Result: "
                    + result.to_string(index=False)
                )

    print("Question:", question)
    print("Generated SQL:", normalized_sql)
    print("Result columns:", list(result.columns))
    print("Chart generated:", chart is not None)

    return {
        "question": question,
        "sql": normalized_sql,
        "result": result_data,
        "answer": answer,
        "chart": chart,
    } 
