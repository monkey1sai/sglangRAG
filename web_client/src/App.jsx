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
  WAITING_REVIEW: "waiting_review",
  COMPLETED: "completed",
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

        if (msg.type === "run_finished") {
          setUiState(UI_STATES.COMPLETED);
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
  const isWaitingReview = uiState === UI_STATES.WAITING_REVIEW;
  const showApproveButton = isWaitingReview && mode !== "autopilot";

  return (
    <div className="page">
      <header className="hero">
        <div className="brand">SAGA 進階版</div>
        <div className="subtitle">自我演化的科學發現系統</div>
        <div className="status-bar">
          <span className={`status-badge ${uiState}`}>
            {uiState === 'idle' ? '閒置' : uiState === 'running' ? '運行中' : uiState === 'waiting_review' ? '等待審核' : '已完成'}
          </span>
          {iteration > 0 && <span className="iteration-badge">迭代輪次：{iteration}</span>}
        </div>
      </header>

      <section className="grid">
        {/* Run Controls Panel */}
        <div className="panel">
          <h2>執行控制</h2>
          <p className="help-text">選擇操作模式並輸入待優化的文字，點擊開始執行即可啟動多輪迭代優化。</p>

          {/* Mode Selection */}
          <label>
            操作模式
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value)}
              disabled={isRunning || isWaitingReview}
            >
              {Object.entries(MODES).map(([key, { label }]) => (
                <option key={key} value={key}>{label}</option>
              ))}
            </select>
          </label>
          <div className="mode-description">{MODES[mode].description}</div>

          <label>
            伺服器連線
            <input
              value={wsUrl}
              onChange={(e) => setWsUrl(e.target.value)}
              disabled={isRunning}
            />
          </label>
          <label>
            待優化文字
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              disabled={isRunning}
              placeholder="請輸入需要優化的文字內容..."
            />
          </label>
          <label>
            關鍵字（逗號分隔）
            <input
              value={keywords}
              onChange={(e) => setKeywords(e.target.value)}
              disabled={isRunning}
              placeholder="例如：準確性, 效率, 品質"
            />
          </label>

          {/* Action Buttons */}
          <div className="button-group">
            <button
              className="primary"
              onClick={startRun}
              disabled={isRunning || isWaitingReview}
            >
              {isPending ? "啟動中..." : "開始執行"}
            </button>

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
          <h2>科學家參數設定</h2>
          <p className="help-text">設定演化迴圈的終止條件與多目標優化權重。</p>

          <div className="param-group">
            <h3>終止條件</h3>
            <label>
              最大迭代次數
              <span className="param-hint">演化達此輪數後自動停止</span>
              <input
                type="number"
                value={maxIters}
                onChange={(e) => setMaxIters(parseInt(e.target.value) || 10)}
                min={1}
                max={100}
                disabled={isRunning}
              />
            </label>
            <label>
              收斂閾值 (ε)
              <span className="param-hint">分數變化小於此值視為收斂</span>
              <input
                type="number"
                value={convergenceEps}
                onChange={(e) => setConvergenceEps(parseFloat(e.target.value) || 0.001)}
                step={0.001}
                disabled={isRunning}
              />
            </label>
            <label>
              收斂耐心值
              <span className="param-hint">連續幾輪無進步後判定收斂</span>
              <input
                type="number"
                value={patience}
                onChange={(e) => setPatience(parseInt(e.target.value) || 3)}
                min={1}
                disabled={isRunning}
              />
            </label>
          </div>

          <div className="param-group">
            <h3>目標設定</h3>
            <label>
              目標權重
              <span className="param-hint">各目標的重要性比例，總和建議為 1</span>
              <input
                value={weights}
                onChange={(e) => setWeights(e.target.value)}
                placeholder="0.4, 0.3, 0.3"
                disabled={isRunning}
              />
            </label>
            <label>
              達標門檻
              <span className="param-hint">各目標達到此分數視為成功</span>
              <input
                value={thresholds}
                onChange={(e) => setThresholds(e.target.value)}
                placeholder="0.8, 0.7, 0.6"
                disabled={isRunning}
              />
            </label>
          </div>
        </div>

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

        {/* Events Panel */}
        <div className="panel events-panel">
          <h2>事件除錯</h2>
          <pre className="events-log">
            {events.map((e, i) => (
              <div key={i} className={`event-line event-${e.type}`}>
                {JSON.stringify(e)}
              </div>
            ))}
          </pre>
        </div>

        {/* System Logs Panel */}
        <div className="panel logs-panel">
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

        {/* Graph JSON Panel */}
        <div className="panel">
          <h2>運算圖 JSON</h2>
          <pre>{graphJson || "(等待中)"}</pre>
        </div>

        {/* Mermaid Panel */}
        <div className="panel">
          <h2>流程圖</h2>
          <MermaidView code={mermaid} />
        </div>
      </section>
    </div>
  );
}
