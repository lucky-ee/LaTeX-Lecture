import { useEffect, useState } from 'react';
import { apiUrl } from './config';

type StageMetric = {
  stage: string;
  total_seconds: number;
  average_seconds: number | null;
  attempts: number;
  errors: number;
};

const stageNames: Record<string, string> = {
  input_check: 'Input checks',
  local_match: 'Local pattern match',
  upstream_request: 'LLM request',
  response_parse: 'Response parsing',
  latex_repair: 'LaTeX repair',
};

function formatSeconds(seconds: number) {
  if (seconds >= 1) return `${seconds.toFixed(2)} s`;
  const ms = seconds * 1000;
  return ms < 0.1 ? '<0.1 ms' : `${ms.toFixed(1)} ms`;
}

export default function StageMetrics() {
  const [stages, setStages] = useState<StageMetric[]>([]);
  const [unavailable, setUnavailable] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    async function refresh() {
      try {
        const response = await fetch(apiUrl('/api/metrics/stages'), { signal: controller.signal });
        if (!response.ok) throw new Error('Metrics unavailable');
        const data: { stages: StageMetric[] } = await response.json();
        if (!controller.signal.aborted) {
          setStages(data.stages);
          setUnavailable(false);
        }
      } catch {
        if (!controller.signal.aborted) setUnavailable(true);
      }
    }
    void refresh();
    const timer = window.setInterval(() => void refresh(), 2000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, []);

  return (
    <section className="stage-metrics" aria-labelledby="metrics-title">
      <h2 id="metrics-title">Processing time</h2>
      <p className="hint">Totals since the backend started, including failed attempts. Updates every 2 seconds.</p>
      {unavailable && <p className="hint" role="status">Metrics unavailable. Retrying… {stages.length > 0 && 'Showing the last readings.'}</p>}
      {!stages.length && !unavailable && <p className="hint">Loading timings…</p>}
      {stages.length > 0 && <div className="metrics-scroll"><table>
        <thead><tr><th>Stage</th><th>Total</th><th>Average</th><th>Attempts</th><th>Errors</th></tr></thead>
        <tbody>{stages.map((stage) => (
          <tr key={stage.stage}>
            <th scope="row">{stageNames[stage.stage] ?? stage.stage}</th>
            <td>{formatSeconds(stage.total_seconds)}</td>
            <td>{stage.average_seconds === null ? '—' : formatSeconds(stage.average_seconds)}</td>
            <td>{stage.attempts}</td><td>{stage.errors}</td>
          </tr>
        ))}</tbody>
      </table></div>}
      <p className="hint">Only executed stages are counted. Transcription and browser rendering are outside these timings.</p>
    </section>
  );
}
