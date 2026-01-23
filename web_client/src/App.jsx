import React, { useMemo, useRef, useState, useCallback, useTransition } from "react";
import MermaidView from "./components/MermaidView.jsx";

const defaultWsUrl = (() => {
  if (typeof window === "undefined") return "ws://localhost:9200/ws/run";
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/ws/run`;
})();

// Operation modes
const MODES = {
  "co-pilot": { label: "Co-pilot (協作模式)", description: "科學家深度參與，審核每一步" },
  "semi-pilot": { label: "Semi-pilot (半自動模式)", description: "僅審核分析報告" },
  "autopilot": { label: "Autopilot (全自動模式)", description: "完全自主運行直到終止" },
};

// UI States
const UI_STATES = {
  IDLE: "idle",
  RUNNING: "running",
  PAUSED: "paused",
  WAITING_REVIEW: "waiting_review",
  COMPLETED: "completed",
};

// Preset Templates
const TEMPLATES = {
  symbolic_regression: {
    name: "符號回歸 (Symbolic Regression)",
    text: "找出擬合以下數據點的數學公式: [(-3,-2),(-2,-4),(-1,-4),(0,-2),(1,2),(2,8),(3,16),(4,26)]",
    keywords: "x²,多項式,擬合,二次",
    mode: "autopilot",
    maxIters: 5,
    weights: "0.5, 0.3, 0.2",
    thresholds: "0.95, 0.5, 0.9",
    convergenceEps: 0.01,
    patience: 2,
  },
  text_optimization: {
    name: "文字優化",
    text: "這是一段測試文字",
    keywords: "準確性,效率,品質",
    mode: "semi-pilot",
    maxIters: 10,
    weights: "0.33, 0.34, 0.33",
    thresholds: "0.7, 0.7, 0.7",
    convergenceEps: 0.001,
    patience: 3,
  },
};

export default function App() {
  const [wsUrl, setWsUrl] = useState(defaultWsUrl);
  const [text, setText] = useState("這是一段測試文字");
  const [keywords, setKeywords] = useState("測試");
  const [events, setEvents] = useState([]);
  const [runId, setRunId] = useState("");
  const [graphJson, setGraphJson] = useState("");
  const [mermaid, setMermaid] = useState("");
  const [logs, setLogs] = useState([]);
  const wsRef = useRef(null);
  const logsEndRef = useRef(null);

  // New state for advanced features
  const [mode, setMode] = useState("semi-pilot");
  const [uiState, setUiState] = useState(UI_STATES.IDLE);
  const [iteration, setIteration] = useState(0);
  const [analysisReport, setAnalysisReport] = useState(null);
  const [isPending, startTransition] = useTransition();

  // Current best result (for stop/export)
  const [currentResult, setCurrentResult] = useState(null);

  // Termination parameters
  const [maxIters, setMaxIters] = useState(10);
  const [convergenceEps, setConvergenceEps] = useState(0.001);
  const [patience, setPatience] = useState(3);

  // Objective parameters
  const [weights, setWeights] = useState("0.33, 0.34, 0.33");
  const [thresholds, setThresholds] = useState("0.7, 0.7, 0.7");

  const keywordList = useMemo(
    () =>
      keywords
        .split(",")
        .map((k) => k.trim())
        .filter(Boolean),
    [keywords],
  );

  const weightList = useMemo(
    () =>
      weights
        .split(",")
        .map((w) => parseFloat(w.trim()))
        .filter((w) => !isNaN(w)),
    [weights],
  );

  const thresholdList = useMemo(
    () =>
      thresholds
        .split(",")
        .map((t) => parseFloat(t.trim()))
        .filter((t) => !isNaN(t)),
    [thresholds],
  );

  const appendEvent = useCallback((evt) => {
    startTransition(() => {
      setEvents((prev) => [...prev, evt]);
    });
  }, []);

  const fetchArtifacts = useCallback(async (rid) => {
    if (!rid) return;
    try {
      const [gRes, mRes] = await Promise.all([
        fetch(`/runs/${rid}/graph.json`),
        fetch(`/runs/${rid}/workflow.mmd`),
      ]);
      startTransition(() => {
        if (gRes.ok) gRes.text().then(setGraphJson);
        if (mRes.ok) mRes.text().then(setMermaid);
      });
    } catch (err) {
      appendEvent({ type: "ui_error", message: String(err) });
    }
  }, [appendEvent]);

  const handleApprove = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "approve", iteration }));
      setUiState(UI_STATES.RUNNING);
      appendEvent({ type: "user_approved", iteration });
    }
  }, [iteration, appendEvent]);

  const handleCancel = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setUiState(UI_STATES.IDLE);
    appendEvent({ type: "user_cancelled" });
  }, [appendEvent]);

  // New: Pause handler
  const handlePause = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "pause" }));
      appendEvent({ type: "user_pause_requested" });
    }
  }, [appendEvent]);

  // New: Resume handler
  const handleResume = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "resume" }));
      appendEvent({ type: "user_resume_requested" });
    }
  }, [appendEvent]);

  // New: Stop handler
  const handleStop = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "stop" }));
      appendEvent({ type: "user_stop_requested" });
    }
  }, [appendEvent]);

  // New: Load template
  const loadTemplate = useCallback((templateKey) => {
    const t = TEMPLATES[templateKey];
    if (t) {
      setText(t.text);
      setKeywords(t.keywords);
      setMode(t.mode);
      setMaxIters(t.maxIters);
      setWeights(t.weights);
      setThresholds(t.thresholds);
      setConvergenceEps(t.convergenceEps);
      setPatience(t.patience);
      appendEvent({ type: "template_loaded", template: templateKey });
    }
  }, [appendEvent]);

  // New: Export result
  const exportResult = useCallback(() => {
    if (!currentResult) return;
    const blob = new Blob([JSON.stringify(currentResult, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `saga_result_${runId || "unknown"}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [currentResult, runId]);

  const startRun = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setEvents([]);
    setLogs([]);
    setGraphJson("");
    setMermaid("");
    setIteration(0);
    setAnalysisReport(null);
    setCurrentResult(null);
    setUiState(UI_STATES.RUNNING);

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      ws.send(
        JSON.stringify({
          type: "start_run",
          text,
          keywords: keywordList,
          mode,
          config: {
            max_iters: maxIters,
            convergence_eps: convergenceEps,
            convergence_patience: patience,
            weights: weightList,
            goal_thresholds: thresholdList,
          },
        }),
      );
    };

    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        appendEvent(msg);

        // Handle different message types
        if (msg.run_id) {
          setRunId(msg.run_id);
        }

        if (msg.type === "iteration_update") {
          startTransition(() => {
            setIteration(msg.iteration || 0);
          });
        }

        if (msg.type === "analysis_report") {
          startTransition(() => {
            setAnalysisReport(msg.report);
          });
        }

        if (msg.type === "need_review") {
          setUiState(UI_STATES.WAITING_REVIEW);
          if (msg.report) {
            setAnalysisReport(msg.report);
          }
        }

        if (msg.type === "mode_changed") {
          setMode(msg.mode);
        }

        // Handle pause/resume states
        if (msg.type === "pause_ack" || msg.type === "run_paused") {
          setUiState(UI_STATES.PAUSED);
        }

        if (msg.type === "resume_ack") {
          setUiState(UI_STATES.RUNNING);
        }

        // Handle stop and export result
        if (msg.type === "run_stopped") {
          setUiState(UI_STATES.COMPLETED);
          if (msg.current_result) {
            setCurrentResult(msg.current_result);
          }
        }

        if (msg.type === "run_finished") {
          setUiState(UI_STATES.COMPLETED);
          setCurrentResult({
            run_id: msg.run_id,
            best_candidate: msg.best_candidate,
            best_score: msg.best_score,
            termination_reason: msg.termination_reason,
            total_iterations: msg.total_iterations,
          });
          if (msg.run_id) {
            fetchArtifacts(msg.run_id);
          }
        }

        if (msg.type === "system_log") {
          startTransition(() => {
            setLogs((prev) => [...prev, msg].slice(-100)); // Keep last 100 logs
          });
          // Scroll to bottom
          setTimeout(() => {
            logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
          }, 100);
        }
      } catch {
        appendEvent({ type: "raw", message: ev.data });
      }
    };

    ws.onclose = () => {
      if (uiState === UI_STATES.RUNNING) {
        setUiState(UI_STATES.IDLE);
      }
      appendEvent({ type: "ws_closed" });
    };

    ws.onerror = () => {
      appendEvent({ type: "ws_error" });
    };
  }, [wsUrl, text, keywordList, mode, maxIters, convergenceEps, patience, weightList, thresholdList, fetchArtifacts, appendEvent, uiState]);

  const isRunning = uiState === UI_STATES.RUNNING;
  const isPaused = uiState === UI_STATES.PAUSED;
  const isWaitingReview = uiState === UI_STATES.WAITING_REVIEW;
  const isCompleted = uiState === UI_STATES.COMPLETED;
  const showApproveButton = isWaitingReview && mode !== "autopilot";

  return (
    <div className="page">
      <header className="hero">
        <div className="brand">SAGA 進階版</div>
        <div className="subtitle">自我演化的科學發現系統</div>
        <div className="status-bar">
          <span className={`status-badge ${uiState}`}>
            {uiState === 'idle' ? '閒置' : uiState === 'running' ? '運行中' : uiState === 'paused' ? '已暫停' : uiState === 'waiting_review' ? '等待審核' : '已完成'}
          </span>
          {iteration > 0 && <span className="iteration-badge">迭代輪次：{iteration}</span>}
        </div>
      </header>

      <section className="grid three-column">
        {/* Left Column: Controls */}
        <div className="column-left">
          {/* Template Selector */}
          <div className="panel">
            <h2>快速模板</h2>
            <div className="template-buttons">
              {Object.entries(TEMPLATES).map(([key, t]) => (
                <button
                  key={key}
                  className="template-btn"
                  onClick={() => loadTemplate(key)}
                  disabled={isRunning || isPaused}
                >
                  {t.name}
                </button>
              ))}
            </div>
          </div>

          {/* Run Controls Panel */}
          <div className="panel">
            <h2>執行控制</h2>

            {/* Mode Selection */}
            <label>
              操作模式
              <select
                value={mode}
                onChange={(e) => setMode(e.target.value)}
                disabled={isRunning || isWaitingReview || isPaused}
              >
                {Object.entries(MODES).map(([key, { label }]) => (
                  <option key={key} value={key}>{label}</option>
                ))}
              </select>
            </label>
            <div className="mode-description">{MODES[mode].description}</div>

            <label>
              待優化文字
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                disabled={isRunning || isPaused}
                placeholder="請輸入需要優化的文字內容..."
              />
            </label>
            <label>
              關鍵字（逗號分隔）
              <input
                value={keywords}
                onChange={(e) => setKeywords(e.target.value)}
                disabled={isRunning || isPaused}
                placeholder="例如：準確性, 效率, 品質"
              />
            </label>

            {/* Action Buttons */}
            <div className="button-group">
              <button
                className="primary"
                onClick={startRun}
                disabled={isRunning || isWaitingReview || isPaused}
              >
                {isPending ? "啟動中..." : "▶ 開始執行"}
              </button>

              {isRunning && (
                <button className="warning" onClick={handlePause}>
                  ⏸ 暫停
                </button>
              )}

              {isPaused && (
                <button className="success" onClick={handleResume}>
                  ▶ 恢復
                </button>
              )}

              {(isRunning || isPaused) && (
                <button className="danger" onClick={handleStop}>
                  ⏹ 停止
                </button>
              )}

              {showApproveButton && (
                <>
                  <button className="success" onClick={handleApprove}>
                    ✓ 批准繼續
                  </button>
                  <button className="danger" onClick={handleCancel}>
                    ✗ 取消執行
                  </button>
                </>
              )}
            </div>

            <div className="meta">執行編號：{runId || "尚未開始"}</div>
          </div>

          {/* Parameter Settings Panel */}
          <div className="panel">
            <h2>參數設定</h2>

            <div className="param-group">
              <h3>終止條件</h3>
              <label>
                最大迭代
                <input
                  type="number"
                  value={maxIters}
                  onChange={(e) => setMaxIters(parseInt(e.target.value) || 10)}
                  min={1}
                  max={100}
                  disabled={isRunning || isPaused}
                />
              </label>
              <label>
                收斂閾值
                <input
                  type="number"
                  value={convergenceEps}
                  onChange={(e) => setConvergenceEps(parseFloat(e.target.value) || 0.001)}
                  step={0.001}
                  disabled={isRunning || isPaused}
                />
              </label>
              <label>
                耐心值
                <input
                  type="number"
                  value={patience}
                  onChange={(e) => setPatience(parseInt(e.target.value) || 3)}
                  min={1}
                  disabled={isRunning || isPaused}
                />
              </label>
            </div>

            <div className="param-group">
              <h3>目標權重</h3>
              <label>
                權重 (逗號分隔)
                <input
                  value={weights}
                  onChange={(e) => setWeights(e.target.value)}
                  placeholder="0.5, 0.3, 0.2"
                  disabled={isRunning || isPaused}
                />
              </label>
              <label>
                達標門檻
                <input
                  value={thresholds}
                  onChange={(e) => setThresholds(e.target.value)}
                  placeholder="0.95, 0.5, 0.9"
                  disabled={isRunning || isPaused}
                />
              </label>
            </div>
          </div>
        </div>

        {/* Middle Column: Main Content */}
        <div className="column-middle">
          {/* Current Result Panel */}
          {currentResult && (
            <div className="panel result-panel">
              <h2>📊 當前結果</h2>
              <div className="result-content">
                <div className="result-item">
                  <strong>最佳候選：</strong>
                  <code className="best-candidate">{currentResult.best_candidate}</code>
                </div>
                <div className="result-item">
                  <strong>分數：</strong> {currentResult.best_score?.toFixed(4)}
                </div>
                {currentResult.termination_reason && (
                  <div className="result-item">
                    <strong>終止原因：</strong> {currentResult.termination_reason}
                  </div>
                )}
              </div>
              <button className="export-btn" onClick={exportResult}>
                📥 導出結果 JSON
              </button>
            </div>
          )}

          {/* Analysis Report Panel */}
          <div className="panel">
            <h2>分析報告</h2>
            {analysisReport ? (
              <div className="report-table">
                <table>
                  <thead>
                    <tr>
                      <th>指標</th>
                      <th>數值</th>
                      <th>狀態</th>
                      <th>趨勢</th>
                    </tr>
                  </thead>
                  <tbody>
                    {analysisReport.report_table?.map((row, idx) => (
                      <tr key={idx} className={`status-${row.status}`}>
                        <td>{row.metric}</td>
                        <td>{row.value}</td>
                        <td>
                          <span className={`status-dot ${row.status}`}></span>
                          {row.status}
                        </td>
                        <td>{row.trend}</td>
                      </tr>
                    )) || (
                        <tr>
                          <td colSpan={4}>尚無數據</td>
                        </tr>
                      )}
                  </tbody>
                </table>
                {analysisReport.suggested_constraints?.length > 0 && (
                  <div className="constraints">
                    <h4>建議新增約束</h4>
                    <ul>
                      {analysisReport.suggested_constraints.map((c, i) => (
                        <li key={i}>{c}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ) : (
              <div className="placeholder">(等待分析中...)</div>
            )}
          </div>

          {/* Mermaid Panel */}
          <div className="panel">
            <h2>流程圖</h2>
            <MermaidView code={mermaid} />
          </div>

          {/* Graph JSON Panel (Collapsible) */}
          <details className="panel">
            <summary><h2 style={{ display: 'inline' }}>運算圖 JSON</h2></summary>
            <pre>{graphJson || "(等待中)"}</pre>
          </details>
        </div>

        {/* Right Column: Logs */}
        <div className="column-right">
          {/* System Logs Panel */}
          <div className="panel logs-panel full-height">
            <h2>系統日誌</h2>
            <div className="logs-container">
              {logs.length === 0 && <div className="placeholder">尚無日誌...</div>}
              {logs.map((log, i) => (
                <div key={i} className={`log-entry log-${log.level}`}>
                  <span className="log-time">
                    {new Date(log.timestamp * 1000).toLocaleTimeString()}
                  </span>
                  <span className="log-msg">{log.message}</span>
                </div>
              ))}
              <div ref={logsEndRef} />
            </div>
          </div>

          {/* Events Panel (Collapsible) */}
          <details className="panel events-panel">
            <summary><h2 style={{ display: 'inline' }}>事件除錯</h2></summary>
            <pre className="events-log" style={{ whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
              {events.map((e, i) => (
                <div key={i} className={`event-line event-${e.type}`}>
                  {JSON.stringify(e)}
                </div>
              ))}
            </pre>
          </details>
        </div>
      </section>
    </div>
  );
}
