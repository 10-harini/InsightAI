import { useCallback, useEffect, useState } from "react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  LineChart,
  Line,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
} from "recharts";
import "./App.css";

const API_URL = "http://127.0.0.1:8000";

function formatValue(value) {
  if (value === null || value === undefined || value === "") return "—";

  if (typeof value === "number" && Number.isFinite(value)) {
    return value.toLocaleString("en-IN", {
      maximumFractionDigits: 2,
    });
  }

  return String(value);
}

function formatCurrency(value) {
  if (
    value === null ||
    value === undefined ||
    !Number.isFinite(Number(value))
  ) {
    return "—";
  }

  return Number(value).toLocaleString("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  });
}

function KpiCard({ icon, label, value, description }) {
  return (
    <article className="kpi-card">
      <div className="kpi-card-top">
        <span className="kpi-icon" aria-hidden="true">
          {icon}
        </span>
        <span className="kpi-label">{label}</span>
      </div>
      <div className="kpi-value">{value}</div>
      <p className="kpi-description">{description}</p>
    </article>
  );
}

// Identify columns that usually contain identifiers rather than measures.
function isIdentifierColumn(column) {
  const name = column.toLowerCase().replace(/[^a-z0-9]/g, "");

  return (
    name === "id" ||
    name.endsWith("id") ||
    name === "index" ||
    name === "serialnumber" ||
    name === "sno" ||
    name === "slno"
  );
}

function buildDynamicKpis(stats) {
  if (!stats) return [];

  const cards = [
    {
      icon: "▦",
      label: "Total Records",
      value: formatValue(stats.total_records),
      description: "Rows in the uploaded dataset",
    },
    {
      icon: "▤",
      label: "Total Columns",
      value: formatValue(stats.total_columns),
      description: "Fields available for analysis",
    },
  ];

  const numericStats = stats.numeric_statistics || {};
  const categoricalStats = stats.categorical_statistics || {};

  const numericColumns = Object.entries(numericStats);
  const categoricalColumns = Object.entries(categoricalStats);

  const meaningfulNumericColumns = numericColumns.filter(
    ([column]) => !isIdentifierColumn(column)
  );

  const preferredMeasures = [
    "revenue",
    "sales",
    "profit",
    "amount",
    "total",
    "marks",
    "score",
    "quantity",
    "units",
    "price",
    "salary",
    "value",
  ];

  function measurePriority(column) {
    const name = column.toLowerCase().replace(/[^a-z0-9]/g, "");

    const index = preferredMeasures.findIndex(
      (measure) => name === measure || name.includes(measure)
    );

    return index === -1 ? preferredMeasures.length : index;
  }

  const sortedNumericColumns = [...meaningfulNumericColumns].sort(
    ([columnA], [columnB]) =>
      measurePriority(columnA) - measurePriority(columnB)
  );

  if (sortedNumericColumns.length > 0) {
    const [column, values] = sortedNumericColumns[0];
    const isRevenue = /revenue|sales|amount|profit/i.test(column);

    cards.push({
      icon: "∑",
      label: `Average ${column}`,
      value: isRevenue
        ? formatCurrency(values.average)
        : formatValue(values.average),
      description: `Mean value of ${column}`,
    });
  } else if (categoricalColumns.length > 0) {
    const [column, values] = categoricalColumns[0];

    cards.push({
      icon: "◉",
      label: `Unique ${column}`,
      value: formatValue(values.unique_values),
      description: `Distinct values in ${column}`,
    });
  }

  if (cards.length < 4 && sortedNumericColumns.length > 0) {
    const [column, values] = sortedNumericColumns[0];
    const isRevenue = /revenue|sales|amount|profit/i.test(column);

    cards.push({
      icon: "↕",
      label: `Maximum ${column}`,
      value: isRevenue
        ? formatCurrency(values.maximum)
        : formatValue(values.maximum),
      description: `Highest value of ${column}`,
    });
  }

  const preferredColumnNames = [
    "student",
    "employee",
    "customer",
    "user",
    "person",
    "name",
  ];

  const preferredColumn = categoricalColumns.find(([column]) => {
    const name = column.toLowerCase().replace(/[^a-z0-9]/g, "");

    return preferredColumnNames.some(
      (preferred) =>
        name === preferred ||
        name === `${preferred}name` ||
        name.endsWith(`${preferred}name`)
    );
  });

  if (preferredColumn && cards.length < 4) {
    const [column, values] = preferredColumn;

    if (!cards.some((card) => card.label === `Unique ${column}`)) {
      cards.push({
        icon: "◈",
        label: `Unique ${column}`,
        value: formatValue(values.unique_values),
        description: `Distinct values in ${column}`,
      });
    }
  }

  for (const [column, values] of categoricalColumns) {
    if (cards.length >= 4) break;

    if (!cards.some((card) => card.label === `Unique ${column}`)) {
      cards.push({
        icon: "◉",
        label: `Unique ${column}`,
        value: formatValue(values.unique_values),
        description: `Distinct values in ${column}`,
      });
    }
  }

  for (const [column, values] of sortedNumericColumns) {
    if (cards.length >= 4) break;

    if (!cards.some((card) => card.label === `Maximum ${column}`)) {
      cards.push({
        icon: "↕",
        label: `Maximum ${column}`,
        value: formatValue(values.maximum),
        description: `Highest value of ${column}`,
      });
    }
  }

  return cards.slice(0, 4);
} 

function InsightChart({ chart }) {
  const [chartType, setChartType] = useState("bar");

  if (!chart?.data?.length || !chart.x_key || !chart.y_key) {
    return (
      <section className="chart-section">
        <div className="chart-heading">
          <div>
            <span className="result-label">DATA VISUALIZATION</span>
            <h4>Chart preview</h4>
          </div>
        </div>

        <div className="chart-empty">
          <span aria-hidden="true">▥</span>
          <p>No chart is available for this result.</p>
          <small>
            Try asking for a numeric value grouped by a category, such as
            revenue by region.
          </small>
        </div>
      </section>
    );
  }

  const data = chart.data.map((item) => ({
    ...item,
    [chart.y_key]: Number(item[chart.y_key]) || 0,
  }));

  const numberFormatter = (value) => formatValue(Number(value));

  return (
    <section className="chart-section">
      <div className="chart-heading">
        <div>
          <span className="result-label">DATA VISUALIZATION</span>
          <h4>{chart.title || `${chart.y_key} by ${chart.x_key}`}</h4>
          <p>
            Horizontal axis: {chart.x_key} · Vertical axis: {chart.y_key}
          </p>
        </div>

        <div className="chart-switch" aria-label="Chart type">
          <button
            type="button"
            className={chartType === "bar" ? "active" : ""}
            aria-pressed={chartType === "bar"}
            onClick={() => setChartType("bar")}
          >
            Bar
          </button>

          <button
            type="button"
            className={chartType === "line" ? "active" : ""}
            aria-pressed={chartType === "line"}
            onClick={() => setChartType("line")}
          >
            Line
          </button>
        </div>
      </div>

      <div className="chart-canvas">
        <ResponsiveContainer width="100%" height="100%">
          {chartType === "line" ? (
            <LineChart
              data={data}
              margin={{ top: 18, right: 20, left: 8, bottom: 48 }}
            >
              <CartesianGrid
                stroke="rgba(255,255,255,0.08)"
                strokeDasharray="4 4"
                vertical={false}
              />

              <XAxis
                dataKey={chart.x_key}
                tick={{ fill: "#a9aec0", fontSize: 11 }}
                axisLine={{ stroke: "#333748" }}
                tickLine={false}
                angle={data.length > 5 ? -25 : 0}
                textAnchor={data.length > 5 ? "end" : "middle"}
                interval="preserveStartEnd"
                height={data.length > 5 ? 65 : 35}
              />

              <YAxis
                tickFormatter={numberFormatter}
                tick={{ fill: "#a9aec0", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                width={75}
              />

              <Tooltip
                contentStyle={{
                  background: "#171a29",
                  border: "1px solid #39334f",
                  borderRadius: "10px",
                  color: "#f2efff",
                }}
                formatter={(value) => [
                  formatValue(Number(value)),
                  chart.y_key,
                ]}
                labelFormatter={(label) => `${chart.x_key}: ${label}`}
              />

              <Legend />

              <Line
                type="monotone"
                dataKey={chart.y_key}
                name={chart.y_key}
                stroke="#a78bfa"
                strokeWidth={3}
                dot={{ fill: "#c4b5fd", r: 4 }}
                activeDot={{ r: 7 }}
                connectNulls={false}
              />
            </LineChart>
          ) : (
            <BarChart
              data={data}
              margin={{ top: 18, right: 20, left: 8, bottom: 48 }}
            >
              <CartesianGrid
                stroke="rgba(255,255,255,0.08)"
                strokeDasharray="4 4"
                vertical={false}
              />

              <XAxis
                dataKey={chart.x_key}
                tick={{ fill: "#a9aec0", fontSize: 11 }}
                axisLine={{ stroke: "#333748" }}
                tickLine={false}
                angle={data.length > 5 ? -25 : 0}
                textAnchor={data.length > 5 ? "end" : "middle"}
                interval="preserveStartEnd"
                height={data.length > 5 ? 65 : 35}
              />

              <YAxis
                tickFormatter={numberFormatter}
                tick={{ fill: "#a9aec0", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                width={75}
              />

              <Tooltip
                cursor={{ fill: "rgba(167,139,250,0.08)" }}
                contentStyle={{
                  background: "#171a29",
                  border: "1px solid #39334f",
                  borderRadius: "10px",
                  color: "#f2efff",
                }}
                formatter={(value) => [
                  formatValue(Number(value)),
                  chart.y_key,
                ]}
                labelFormatter={(label) => `${chart.x_key}: ${label}`}
              />

              <Legend />

              <Bar
                dataKey={chart.y_key}
                name={chart.y_key}
                fill="#a78bfa"
                radius={[7, 7, 0, 0]}
                maxBarSize={65}
              />
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
    </section>
  );
}


function App() {
  const [file, setFile] = useState(null);
  const [question, setQuestion] = useState("");
  const [uploadMessage, setUploadMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const [dashboardStats, setDashboardStats] = useState(null);
  const [statsLoading, setStatsLoading] = useState(true);
  const [statsError, setStatsError] = useState("");

  const fetchDashboardStats = useCallback(async () => {
    setStatsLoading(true);
    setStatsError("");

    try {
      const response = await fetch(`${API_URL}/dashboard-stats`);
      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data.detail || "Could not load dashboard statistics."
        );
      }

      setDashboardStats(data);
    } catch (err) {
      setStatsError(`${err.message}. Make sure the backend is running.`);
    } finally {
      setStatsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDashboardStats();
  }, [fetchDashboardStats]);

  async function handleUpload() {
    if (!file) {
      setError("Please select a CSV file first.");
      return;
    }

    setLoading(true);
    setError("");
    setUploadMessage("");
    setResult(null);

    try {
      const formData = new FormData();
      formData.append("file", file);

      const response = await fetch(`${API_URL}/upload`, {
        method: "POST",
        body: formData,
      });

      const data = await response.json();

      if (!response.ok || data.error) {
        throw new Error(data.error || data.detail || "Upload failed.");
      }

      // Read the actual keys returned by the backend.
      const rowCount = Number.isFinite(Number(data.rows))
        ? Number(data.rows)
        : Number.isFinite(Number(data.total_records))
          ? Number(data.total_records)
          : null;

      const columnCount = Array.isArray(data.columns)
        ? data.columns.length
        : Number.isFinite(Number(data.total_columns))
          ? Number(data.total_columns)
          : null;

      setUploadMessage(
        rowCount !== null && columnCount !== null
          ? `Uploaded successfully! ${rowCount} rows and ${columnCount} columns detected.`
          : `Uploaded successfully! ${file.name} is ready to analyze.`
      );

      await fetchDashboardStats();
    } catch (err) {
      setError(
        `Upload failed: ${err.message}. Make sure your Python backend is running.`
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleAsk(event) {
    event.preventDefault();

    if (!question.trim()) {
      setError("Please enter a question.");
      return;
    }

    setLoading(true);
    setError("");
    setResult(null);

    try {
      const response = await fetch(
        `${API_URL}/ask?question=${encodeURIComponent(question)}`,
        { method: "POST" }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data.detail || data.error || "Analysis request failed."
        );
      }

      const unavailableMessage =
        data.answer ||
        data.details ||
        data.error ||
        "The requested information is not available in this dataset.";

      if (
        data.error &&
        !data.answer &&
        !data.details &&
        !data.sql &&
        (!data.result || data.result.length === 0)
      ) {
        setResult({
          question,
          answer: unavailableMessage,
          sql: null,
          result: [],
          chart: null,
        });
      } else {
        setResult({
          ...data,
          answer: data.answer || data.details || unavailableMessage,
          result: Array.isArray(data.result) ? data.result : [],
          chart: data.chart || null,
        });
      }
    } catch (err) {
      setError(
        `Analysis failed: ${err.message}. Check that the backend is running and a CSV has been uploaded.`
      );
    } finally {
      setLoading(false);
    }
  }

  const hasDataset = dashboardStats?.dataset_loaded === true;
  const dynamicKpis = buildDynamicKpis(dashboardStats?.statistics);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <div className="brand-icon">✦</div>
          <div>
            <h1>InsightAI</h1>
            <p>AI DATA ANALYST</p>
          </div>
        </div>

        <div className="status">
          <span className="status-dot" />
          AI Analytics Workspace
        </div>
      </header>

      <main className="main">
        <section className="hero">
          <span className="eyebrow">YOUR DATA, UNDERSTOOD</span>
          <h2>
            Ask questions.
            <br />
            <span>Discover insights.</span>
          </h2>
          <p>
            Upload a CSV dataset and use natural language to explore your data,
            generate SQL, and discover patterns.
          </p>
        </section>

        <section className="dashboard-section">
          <div className="dashboard-heading">
            <div>
              <span className="eyebrow">YOUR OVERVIEW</span>
              <h3>Dashboard overview</h3>
              <p>
                {hasDataset
                  ? `${formatValue(dashboardStats.rows)} rows · ${
                      dashboardStats.columns?.length ?? 0
                    } columns`
                  : "Upload a dataset to calculate your key metrics."}
              </p>
            </div>

            <button
              type="button"
              className="button secondary"
              onClick={fetchDashboardStats}
              disabled={statsLoading}
            >
              {statsLoading ? "Refreshing..." : "↻ Refresh"}
            </button>
          </div>

          {statsError && (
            <div className="message error" role="alert">
              {statsError}
            </div>
          )}

          {statsLoading && !dashboardStats ? (
            <div className="message">Loading dashboard statistics...</div>
          ) : hasDataset && dynamicKpis.length > 0 ? (
            <div className="kpi-grid">
              {dynamicKpis.map((card) => (
                <KpiCard key={card.label} {...card} />
              ))}
            </div>
          ) : (
            !statsLoading &&
            !statsError && (
              <div className="message">
                No dataset is loaded yet. Upload a CSV below to populate the
                dashboard.
              </div>
            )
          )}
        </section>

        {error && (
          <div className="message error" role="alert">
            {error}
          </div>
        )}

        <section className="panel upload-panel">
          <div className="section-heading">
            <div className="number">01</div>
            <div>
              <h3>Upload your dataset</h3>
              <p>Start with a CSV file containing your data.</p>
            </div>
          </div>

          <label className="upload-box">
            <span className="upload-icon">↑</span>
            <strong>{file ? file.name : "Choose a CSV file"}</strong>
            <span>
              {file ? "File selected" : "Select a file from your computer"}
            </span>
            <input
              type="file"
              accept=".csv,text/csv"
              onChange={(event) => {
                setFile(event.target.files?.[0] || null);
                setUploadMessage("");
                setError("");
              }}
            />
          </label>

          <button
            className="button primary"
            onClick={handleUpload}
            disabled={loading || !file}
          >
            {loading ? "Please wait..." : "Upload dataset"}
          </button>

          {uploadMessage && (
            <div className="message success" role="status">
              {uploadMessage}
            </div>
          )}
        </section>

        <section className="panel question-panel">
          <div className="section-heading">
            <div className="number">02</div>
            <div>
              <h3>Ask your data</h3>
              <p>Ask a question in plain English.</p>
            </div>
          </div>

          <form onSubmit={handleAsk}>
            <label className="field-label" htmlFor="question">
              YOUR QUESTION
            </label>

            <textarea
              id="question"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Example: Show total revenue by category."
              rows={3}
            />

            <div className="examples">
              <span>Try asking:</span>
              {[
                "Show total revenue by category.",
                "Which product has the highest revenue?",
                "Show revenue by region.",
              ].map((example) => (
                <button
                  className="example-chip"
                  type="button"
                  key={example}
                  onClick={() => setQuestion(example)}
                >
                  {example}
                </button>
              ))}
            </div>

            <button
              className="button primary"
              type="submit"
              disabled={loading || !question.trim()}
            >
              {loading ? "Analyzing..." : "✦  Analyze data"}
            </button>
          </form>
        </section>

        {result && (
          <section className="panel results-panel">
            <div className="section-heading">
              <div className="number">03</div>
              <div>
                <h3>Analysis results</h3>
                <p>Your question, answered using your dataset.</p>
              </div>
            </div>

            <div className="answer-card">
              <span className="result-label">AI INSIGHT</span>
              <p>{result.answer || "Analysis completed."}</p>
            </div>

            <InsightChart chart={result.chart} />

            <div className="table-section">
              <h4>Query results</h4>

              {result.result?.length > 0 ? (
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        {Object.keys(result.result[0]).map((column) => (
                          <th key={column}>{column}</th>
                        ))}
                      </tr>
                    </thead>

                    <tbody>
                      {result.result.map((row, index) => (
                        <tr key={index}>
                          {Object.entries(row).map(([column, value]) => (
                            <td key={column}>{formatValue(value)}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="chart-empty">
                  <p>No rows were returned for this question.</p>
                  <small>
                    Try changing your question and analyze again.
                  </small>
                </div>
              )}
            </div>

            {result.sql && (
              <details className="sql-details">
                <summary>View generated SQL</summary>
                <pre>{result.sql}</pre>
              </details>
            )}
          </section>
        )}

        <footer>
          <span>InsightAI</span>
          <span>Python · FastAPI · SQLite · Gemini · React · Recharts</span>
        </footer>
      </main>
    </div>
  );
}

export default App;