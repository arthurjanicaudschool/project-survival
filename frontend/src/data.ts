import { useEffect, useState } from "react";
import { createClient } from "@supabase/supabase-js";
import type { State } from "./types";
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
    setState(null);
    setError("");
    setLoading(true);
    const refresh = async () => {
      if (running) return;
      running = true;
      lastRefresh=Date.now();
      try {
        let result: State | null;
        if (demo) {
          const r = await fetch(experiment === "survival-002" ? "/demo-phase2.json" : "/demo.json");
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
            .maybeSingle();
          if (version.error) throw version.error;
          if (version.data?.updated_at === lastVersion) {
            if (active) setError("");
            return;
          }
          const { data, error } = await supabase
            .from("dashboard_states")
            .select("payload")
            .eq("experiment_id", eid)
            .maybeSingle();
          if (error) throw error;
          result = data?.payload || null;
          if (result && result.mode !== "live")
            throw Error("Données synthétiques interdites dans la vue réelle.");
          lastVersion = version.data?.updated_at || "";
        }
        if (active) {
          setState(result);
          setError("");
        }
      } catch (e) {
        if (active)
          setError(
            e instanceof Error ? e.message : "Synchronisation indisponible",
          );
      } finally {
        running = false;
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
      clearInterval(interval);
      if(pending)clearTimeout(pending);
      if (channel && supabase) void supabase.removeChannel(channel);
    };
  }, [demo, experiment]);
  return { state, error, loading, realtime };
}
