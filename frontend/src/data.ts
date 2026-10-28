import { useEffect, useState } from "react";
import { createClient } from "@supabase/supabase-js";
import type { State } from "./types";
import { cacheConfirmed, confirmedState, connectionError, readConfirmed } from "./data-cache";
const env = import.meta.env;
export const supabase =
  env.VITE_SUPABASE_URL && env.VITE_SUPABASE_ANON_KEY
    ? createClient(env.VITE_SUPABASE_URL, env.VITE_SUPABASE_ANON_KEY)
    : null;
export function useCompetition(demo: boolean, experiment = env.VITE_EXPERIMENT_ID || "survival-001") {
  const [state, setState] = useState<State | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [realtime,setRealtime]=useState("CONNECTING");
  useEffect(() => {
    let active = true,
      lastVersion = "",
      running = false,
      lastRefresh=0;
    let pending: ReturnType<typeof setTimeout> | undefined;
    let request: AbortController | undefined;
    setState(demo ? null : readConfirmed(experiment));
    setError("");
    setLoading(true);
    const refresh = async () => {
      if (running) return;
      running = true;
      lastRefresh=Date.now();
      const controller = new AbortController();
      request = controller;
      const timeout = setTimeout(() => controller.abort(), 20000);
      try {
        let result: State | null;
        if (demo) {
          const r = await fetch(experiment === "survival-002" ? "/demo-phase2.json" : "/demo.json", {signal: controller.signal});
          if (!r.ok)
            throw Error(
              "Exécutez python -m survival.cli demo pour générer les fixtures.",
            );
          result = await r.json();
          if (result?.mode !== "demo")
            throw Error("Source de démonstration invalide.");
        } else {
          if (!supabase)
            throw Error(
              "Supabase non configuré. Connectez vos variables publiques pour suivre la compétition.",
            );
          const eid = experiment;
          const version = await supabase
            .from("dashboard_updates")
            .select("updated_at")
            .eq("experiment_id", eid)
            .abortSignal(controller.signal)
            .maybeSingle();
          if (version.error) throw {status: version.status};
          if (version.data?.updated_at === lastVersion) {
            if (active) setError("");
            return;
          }
          const { data, error, status } = await supabase
            .from("dashboard_states")
            .select("payload")
            .eq("experiment_id", eid)
            .abortSignal(controller.signal)
            .maybeSingle();
          if (error) throw {status};
          result = data?.payload || null;
          if (result && !confirmedState(result, experiment))
            throw Error("Source réelle invalide.");
          lastVersion = version.data?.updated_at || "";
          if (result && active) cacheConfirmed(experiment, result);
        }
        if (active) {
          setState(result);
          setError("");
        }
      } catch (e) {
        if (active)
          setError(
            demo && e instanceof Error ? e.message : connectionError(e, controller.signal.aborted),
          );
      } finally {
        running = false;
        clearTimeout(timeout);
        if (request === controller) request = undefined;
        if (active) setLoading(false);
      }
    };
    void refresh();
    const interval = setInterval(refresh, 60000);
    const channel =
      !demo && supabase
        ? supabase
            .channel("survival-dashboard")
            .on(
              "postgres_changes",
              {
                event: "*",
                schema: "public",
                table: "dashboard_updates",
                filter: `experiment_id=eq.${experiment}`,
              },
              () => {if(pending)return;pending=setTimeout(()=>{pending=undefined;void refresh();},Math.max(0,60000-(Date.now()-lastRefresh)));},
            )
            .subscribe(status => {if(active)setRealtime(status);})
        : null;
    return () => {
      active = false;
      request?.abort();
      clearInterval(interval);
      if(pending)clearTimeout(pending);
      if (channel && supabase) void supabase.removeChannel(channel);
    };
  }, [demo, experiment]);
  return { state, error, loading, realtime };
}
