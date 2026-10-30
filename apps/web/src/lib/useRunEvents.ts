"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { eventsUrl, getWorkflow } from "./api";
import { reduceEvents } from "./timeline";
import type { RunEvent, WorkflowRun } from "./types";

export type Connection = "connecting" | "live" | "reconnecting" | "closed" | "not-found" | "rejected";

const snapshot = (run: WorkflowRun): RunEvent =>
  ({ id: `refetch-${Date.now()}`, type: "run.snapshot", workflow_run_id: run.id, agent: null, ts: new Date().toISOString(), data: { run } });

/** Live timeline for one run. Reconnects with backoff; every (re)connect starts with a server snapshot,
 * so events missed while disconnected are covered by fresh state. */
export function useRunEvents(runId: string) {
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [connection, setConnection] = useState<Connection>("connecting");
  const [epoch, setEpoch] = useState(0); // bump to reconnect after the socket closed (e.g. a finished run was reopened)

  useEffect(() => {
    let ws: WebSocket | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let tries = 0;
    let stopped = false;

    const open = () => {
      ws = new WebSocket(eventsUrl(runId));
      ws.onopen = () => {
        tries = 0;
        setConnection("live");
      };
      ws.onmessage = (m) => setEvents((es) => [...es, JSON.parse(m.data) as RunEvent]);
      ws.onclose = (e) => {
        if (stopped) return;
        if (e.code === 4404) return setConnection("not-found");
        if (e.code === 1008) return setConnection("rejected"); // origin not in WEB_ORIGINS
        if (e.code === 1000) {
          // run finished: refetch so the page has the final report, not the state at connect time
          setConnection("closed");
          getWorkflow(runId)
            .then((run) => !stopped && setEvents((es) => [...es, snapshot(run)]))
            .catch(() => {});
          return;
        }
        setConnection("reconnecting");
        timer = setTimeout(open, Math.min(1000 * 2 ** tries++, 15_000));
      };
    };
    open();
    return () => {
      stopped = true;
      clearTimeout(timer);
      ws?.close();
    };
  }, [runId, epoch]);

  const timeline = useMemo(() => reduceEvents(events), [events]);
  const reopen = useCallback(() => setEpoch((n) => n + 1), []);
  return { timeline, connection, reopen };
}
