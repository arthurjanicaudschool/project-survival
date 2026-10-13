import React, { useState, useEffect } from "react";
import { createRoot } from "react-dom/client";
import {
  AreaChart,
  Area,
  LineChart,
  Line,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  Legend,
} from "recharts";
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  ArrowUpRight as External,
  ChartNoAxesCombined,
  ChevronRight,
  Clock3,
  Database,
  FlaskConical,
  Globe2,
  LayoutDashboard,
  Radio,
  Shield,
  Terminal,
  Trophy,
  Users,
  Zap,
  Download,
  Search,
  X,
  Play,
} from "lucide-react";
import { useCompetition } from "./data";
import type { Agent, State, Snapshot } from "./types";
import "./style.css";

const colors = [
  "#c9f36c",
  "#71b9f8",
  "#ab9bf3",
  "#f3be73",
  "#eb83aa",
  "#5fd6ad",
  "#5bd0dd",
  "#db9fec",
  "#e9dd77",
  "#e78672",
];
const euro = (n: unknown) =>
  new Intl.NumberFormat("fr-FR", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 2,
  }).format(Number(n || 0));
const pct = (n: unknown) =>
  `${Number(n || 0) >= 0 ? "+" : ""}${(Number(n || 0) * 100).toFixed(2)} %`;
const num = (n: unknown) =>
  Number(n || 0).toLocaleString("fr-FR", { maximumFractionDigits: 2 });
const time = (s: string) =>
  new Date(s).toLocaleTimeString("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
const nav = (a: Agent) => Number(a.snapshot?.nav_eur ?? a.initial_eur);
const roi = (a: Agent) => Number(a.snapshot?.roi || 0);
const rank = (agents: Agent[]) =>
  [...agents].sort(
    (a, b) => roi(b) - roi(a) || Number(a.id.slice(1)) - Number(b.id.slice(1)),
  );
const navItems = [
  { label: "Overview", icon: LayoutDashboard },
  { label: "Leaderboard", icon: Trophy },
  { label: "Performance", icon: ChartNoAxesCombined },
  { label: "Agents", icon: Users },
  { label: "Live activity", icon: Activity },
  { label: "Market explorer", icon: Globe2 },
];

function EquityChart({
  state,
  selected,
  normalized = false,
}: {
  state: State;
  selected?: string;
  normalized?: boolean;
}) {
  const rows = state.history.map((p) =>
    Object.fromEntries([
      ["at", p.at],
      ...state.agents.map((a) => {
        const s = p[a.id] as Snapshot | undefined;
        return [
          a.id,
          s ? (normalized ? Number(s.roi) * 100 : Number(s.nav_eur)) : null,
        ];
      }),
    ]),
  );
  const agents = selected
    ? state.agents.filter((a) => a.id === selected)
    : state.agents;
  if (!rows.length)
    return (
      <div className="chart-empty">
        La première valorisation apparaîtra après un cycle.
      </div>
    );
  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart
        data={rows}
        margin={{ top: 15, right: 10, left: 0, bottom: 0 }}
      >
        <CartesianGrid
          stroke="#232a33"
          strokeDasharray="3 5"
          vertical={false}
        />
        <XAxis
          dataKey="at"
          tickFormatter={(v) => time(v).slice(0, 5)}
          stroke="#66717f"
          fontSize={11}
          minTickGap={60}
        />
        <YAxis
          stroke="#66717f"
          fontSize={11}
          tickFormatter={(v) => (normalized ? `${v}%` : `€${v}`)}
          width={48}
          domain={["auto", "auto"]}
        />
        <Tooltip
          contentStyle={{
            background: "#141a22",
            border: "1px solid #303943",
            borderRadius: 10,
          }}
          labelFormatter={(v) => new Date(String(v)).toLocaleString("fr-FR")}
          formatter={(v) =>
            normalized ? `${Number(v).toFixed(2)} %` : euro(v)
          }
        />
        {agents.map((a) => (
          <Line
            key={a.id}
            type="linear"
            dataKey={a.id}
            name={`${a.id} ${a.name}`}
            stroke={colors[Number(a.id.slice(1)) - 1]}
            strokeWidth={2}
            dot={rows.length === 1}
            connectNulls={false}
            isAnimationActive={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
function Badge({ agent }: { agent: Agent }) {
  return (
    <span className={`risk ${agent.dynamic ? "dynamic" : ""}`}>
      {agent.dynamic ? <Zap size={11} /> : <Shield size={11} />}{" "}
        {agent.risk.prudence_enabled === false ? "Libre" : agent.dynamic ? "Dynamique" : "Prudent"}
    </span>
  );
}
function AgentName({ agent, onClick }: { agent: Agent; onClick?: () => void }) {
  return (
    <button className="agent-name" onClick={onClick}>
      <span
        className="avatar"
        style={{
          color: colors[Number(agent.id.slice(1)) - 1],
          background: colors[Number(agent.id.slice(1)) - 1] + "13",
        }}
      >
        {agent.id}
      </span>
      <span>
        <strong>{agent.name}</strong>
        <small>
          {agent.initial_eur} EUR ·{" "}
          {agent.dynamic ? "Growth seeker" : "Strategic trader"}
        </small>
      </span>
    </button>
  );
}
function Kpi({
  label,
  value,
  sub,
  positive,
}: {
  label: string;
  value: string;
  sub: string;
  positive?: boolean;
}) {
  return (
    <div className="kpi">
      <p>{label}</p>
      <strong
        className={
          positive === undefined ? "" : positive ? "positive" : "negative"
        }
      >
        {value}
      </strong>
      <span>{sub}</span>
    </div>
  );
}
function Leaderboard({
  state,
  onSelect,
  compact = false,
}: {
  state: State;
  onSelect: (a: Agent) => void;
  compact?: boolean;
}) {
  const [filter, setFilter] = useState("Tous");
  const agents = rank(state.agents).filter(
    (a) =>
      filter === "Tous" ||
      (filter === "10 EUR" && a.initial_eur === "10") ||
      (filter === "50 EUR" && a.initial_eur === "50") ||
      (filter === "Dynamiques" && a.dynamic) ||
      (filter === "Standards" && !a.dynamic),
  );
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>
            Classement des agents <span className="count">10</span>
          </h2>
          <p>Le rendement net fait la différence.</p>
        </div>
        <span className="subtle">
          TRI PAR ROI NET <ArrowDownRight size={13} />
        </span>
      </div>
      {!compact && (
        <div className="filters">
          {["Tous", "10 EUR", "50 EUR", "Dynamiques", "Standards"].map((f) => (
            <button
              key={f}
              className={f === filter ? "selected" : ""}
              onClick={() => setFilter(f)}
            >
              {f}
            </button>
          ))}
        </div>
      )}
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>RANG</th>
              <th>AGENT</th>
              <th>VALEUR NETTE</th>
              <th>P&L NET</th>
              <th>ROI</th>
              {!compact && (
                <>
                  <th>MAX. DRAWDOWN</th>
                  <th>WIN RATE</th>
                  <th>IMMOBILISÉ</th>
                </>
              )}
              <th>TRADES</th>
              <th>PROFIL</th>
            </tr>
          </thead>
          <tbody>
            {agents.map((a) => (
              <tr key={a.id}>
                <td>
                  <span
                    className={
                      rank(state.agents)[0].id === a.id ? "rank-first" : "rank"
                    }
                  >
                    {rank(state.agents).findIndex((x) => x.id === a.id) + 1 < 10
                      ? "0"
                      : ""}
                    {rank(state.agents).findIndex((x) => x.id === a.id) + 1}
                  </span>
                </td>
                <td>
                  <AgentName agent={a} onClick={() => onSelect(a)} />
                </td>
                <td className="mono">
                  {euro(nav(a))}
                  {!!a.snapshot?.stranded.length && (
                    <small className="warning">Borne basse</small>
                  )}
                </td>
                <td
                  className={`mono ${nav(a) >= Number(a.initial_eur) ? "positive" : "negative"}`}
                >
                  {euro(nav(a) - Number(a.initial_eur))}
                </td>
                <td>
                  <span
                    className={`roi ${roi(a) >= 0 ? "positive" : "negative"}`}
                  >
                    {pct(roi(a))}
                  </span>
                </td>
                {!compact && (
                  <>
                    <td>{pct(-Number(a.stats.max_drawdown))}</td>
                    <td>
                      {a.stats.closed
                        ? `${((100 * a.stats.wins) / a.stats.closed).toFixed(0)} %`
                        : "—"}
                    </td>
                    <td>
                      {euro(
                        Number(a.snapshot?.invested_cost || 0) /
                          Number(state.fx.usd_per_eur),
                      )}
                    </td>
                  </>
                )}
                <td className="mono">{a.stats.trades}</td>
                <td>
                  <Badge agent={a} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="panel-foot">
        <span>
          <Shield size={13} /> Portefeuilles indépendants · capital 100 % fictif
        </span>
        <span>
          {state.agents.filter((a) => nav(a) > Number(a.initial_eur)).length} /
          10 en territoire positif
        </span>
      </div>
    </section>
  );
}
function Feed({ state, limit }: { state: State; limit?: number }) {
  const rows = [...state.events].reverse().slice(0, limit);
  return (
    <div className="feed">
      {rows.length ? (
        rows.map((e) => (
          <article key={e.id}>
            <span
              className={`event-dot ${e.kind === "ERROR" || e.kind === "REJECTION" || e.kind === "RESEARCH_ERROR" ? "amber" : ""}`}
            />
            <div>
              <div className="event-title">
                <strong>{e.agent_id || "SYSTEM"}</strong>
                <span>{e.kind}</span>
                <time>{time(e.at)}</time>
              </div>
              <p>{e.message}</p>
              {e.details && ["RESEARCH", "RESEARCH_ERROR", "LLM_USAGE", "CYCLE_COMPLETE", "POLICY_CHANGE"].includes(e.kind) && (
                <details><summary>Preuve et détails techniques</summary><pre className="audit-json">{JSON.stringify(e.details, null, 2)}</pre></details>
              )}
            </div>
          </article>
        ))
      ) : (
        <p className="empty">Aucun événement enregistré.</p>
      )}
    </div>
  );
}
function Overview({
  state,
  onSelect,
  onPage,
}: {
  state: State;
  onSelect: (a: Agent) => void;
  onPage: (p: string) => void;
}) {
  const total = state.agents.reduce((s, a) => s + nav(a), 0),
    initial = state.agents.reduce((s, a) => s + Number(a.initial_eur), 0),
    ranked = rank(state.agents);
  const consolidated = state.history.map((p) => ({
    at: p.at,
    value: state.agents.reduce(
      (sum, a) => sum + Number((p[a.id] as Snapshot)?.nav_eur || a.initial_eur),
      0,
    ),
  }));
  return (
    <>
      <div className="intro">
        <div className="eyebrow">
          <span className="live-dot" /> THE EXPERIMENT IS{" "}
          {state.status === "FINISHED" ? "COMPLETE" : "RUNNING"}
        </div>
        <h1>La survie est une stratégie.</h1>
        <p>Dix intelligences. Leurs marchés. Leurs décisions. Une seule place au sommet.</p>
      </div>
      <div className="kpi-grid">
        <Kpi
          label="VALEUR TOTALE"
          value={euro(total)}
          sub={`${euro(initial)} de capital initial fictif`}
        />
        <Kpi
          label="BÉNÉFICE NET"
          value={euro(total - initial)}
          sub="Frais et spread inclus"
          positive={total >= initial}
        />
        <Kpi
          label="ROI CONSOLIDÉ"
          value={pct(total / initial - 1)}
          sub="Conversion EUR figée au lancement"
          positive={total >= initial}
        />
        <Kpi
          label="AGENTS EN COMPÉTITION"
          value={`${state.agents.length} / 10`}
          sub={`${state.agents.reduce((s, a) => s + a.stats.trades, 0)} transactions fictives enregistrées`}
        />
      </div>
      <section className="panel padded">
        <h2>État du moteur et preuves de fonctionnement</h2>
          {state.agents.some(a => a.participation?.required) && <div>
            <h3>Participation HUNTER / SPRINTER</h3>
            <p className="subtle">Premier investissement sous 24 h : opportunité stratégique ou petite exploration choisie par l’IA. Exploration : cible 10 % du capital initial, maximum 20 % frais inclus selon les minimums réels. Aucun rendement positif présumé.</p>
            {state.agents.filter(a => a.participation?.required).map(a => <p key={a.id} className={a.participation?.status === "OVERDUE" ? "negative" : a.participation?.status === "FULFILLED" ? "positive" : "subtle"}>
              {a.id} {a.name} · {a.participation?.status === "FULFILLED" ? "Premier investissement effectué" : a.participation?.status === "OVERDUE" ? "Échéance dépassée — participation non remplie" : "Premier investissement en attente"}
              {a.participation?.deadline && ` · échéance ${new Date(a.participation.deadline).toLocaleString("fr-FR")}`}
            </p>)}
          </div>}
          {state.agents.some(a => (a.last_analysis || a.runtime)?.status === "TECHNICAL_ERROR") &&
            <p className="negative" role="alert">Une ou plusieurs dernières analyses ont échoué. Une actualisation sans nouvelle analyse ne résout pas cette panne ; consultez les diagnostics des agents.</p>}
          {state.status !== "FINISHED" && Date.now() - new Date(state.health?.completed_at || state.updated_at).getTime() > 20 * 60000 &&
            <p className="negative" role="alert"><strong>Cycle en retard : aucune mise à jour enregistrée depuis {Math.floor((Date.now() - new Date(state.health?.completed_at || state.updated_at).getTime()) / 60000)} minutes.</strong> Une ancienne exécution automatique réussie ne garantit pas la cadence actuelle.</p>}
        {state.health ? <>
          <p>Dernier cycle terminé : {new Date(state.health.completed_at).toLocaleString("fr-FR")} · {state.health.duration_seconds}s · {state.health.market_count} marchés · {state.health.cycle_count} cycles enregistrés.</p>
          <p className={state.health.market_provider_ok ? "positive" : "negative"}>Polymarket : {state.health.market_provider_ok ? "données reçues" : "indisponible"} · politique {state.health.policy_version}</p>
          <p>Dernier cycle du cron GitHub : {state.health.last_scheduled_cycle ? new Date(state.health.last_scheduled_cycle).toLocaleString("fr-FR") : "aucun confirmé"} · dernier déclencheur : {state.health.trigger_source || state.health.trigger || "inconnu"}</p>
          <p>Dernier cycle du secours Supabase : {state.health.last_watchdog_cycle ? new Date(state.health.last_watchdog_cycle).toLocaleString("fr-FR") : "aucun confirmé — activation et vérification nécessaires"}.</p>
          {state.health.logs_url && <a href={state.health.logs_url} target="_blank" rel="noreferrer">Voir les logs GitHub du cycle <External size={12}/></a>}
        </> : <p>En attente d'un cycle avec diagnostic. Aucun état technique n'est inventé.</p>}
        <div className="table-scroll"><table><thead><tr><th>AGENT</th><th>ÉTAT</th><th>DERNIÈRE ANALYSE</th><th>REQUÊTES AZURE MESURÉES</th><th>TOKENS ENTRÉE / SORTIE</th></tr></thead><tbody>
          {state.agents.map(a => <tr key={a.id}><td>{a.id} {a.name}</td><td>{a.runtime?.status || "Non mesuré"}{a.last_analysis && <small className="subtle"> · dernière analyse : {a.last_analysis.status}</small>}</td><td>{a.memory.last_call ? new Date(a.memory.last_call).toLocaleString("fr-FR") : "Aucune"}</td><td>{a.stats.llm_usage?.requests ?? "Non mesuré"}</td><td>{a.stats.llm_usage ? `${a.stats.llm_usage.prompt_tokens} / ${a.stats.llm_usage.completion_tokens}` : "Non mesuré"}</td></tr>)}
        </tbody></table></div>
        <p className="subtle">WAIT / HOLD = choix de l'agent · NOT_DUE = prochaine session pas encore due · EXECUTION_REJECTED = ordre non exécuté · TECHNICAL_ERROR / PROVIDER_ERROR = panne. Tokens comptés depuis l'activation de la mesure ; l'historique antérieur est inconnu.</p>
      </section>
      <div className="overview-grid">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Capital de l'arène</h2>
              <p>Valeur liquidable des dix portefeuilles, en EUR</p>
            </div>
            <span className="chart-tag">7 JOURS</span>
          </div>
          <div className="aggregate-value">
            {euro(total)}{" "}
            <span className={total >= initial ? "positive" : "negative"}>
              {pct(total / initial - 1)} <ArrowUpRight size={15} />
            </span>
          </div>
          <ResponsiveContainer width="100%" height={225}>
            <AreaChart
              data={consolidated}
              margin={{ top: 15, right: 20, left: 0, bottom: 0 }}
            >
              <defs>
                <linearGradient id="capital" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#c9f36c" stopOpacity={0.2} />
                  <stop offset="100%" stopColor="#c9f36c" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid
                stroke="#242a33"
                vertical={false}
                strokeDasharray="3 6"
              />
              <XAxis
                dataKey="at"
                tickFormatter={(v) => time(v).slice(0, 5)}
                fontSize={11}
                stroke="#66717f"
              />
              <YAxis
                domain={["auto", "auto"]}
                tickFormatter={(v) => `€${v}`}
                fontSize={11}
                stroke="#66717f"
              />
              <Tooltip
                contentStyle={{
                  background: "#141a22",
                  border: "1px solid #303943",
                }}
                formatter={(v) => euro(v)}
                labelFormatter={(v) =>
                  new Date(String(v)).toLocaleString("fr-FR")
                }
              />
              <Area
                dataKey="value"
                name="Capital"
                type="linear"
                stroke="#c9f36c"
                strokeWidth={2}
                fill="url(#capital)"
                dot={consolidated.length === 1}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
          <div className="chart-caption">
            <span className="legend-dot" /> Capital consolidé{" "}
            <span>
              Source :{" "}
              {state.mode === "demo"
                ? "fixtures synthétiques"
                : "carnets Polymarket"}{" "}
              · frais déduits
            </span>
          </div>
        </section>
        <section className="panel spotlight">
          <div className="panel-heading">
            <h2>En tête de l'arène</h2>
            <Trophy size={18} className="lime" />
          </div>
          <div className="leader-emblem">
            <Terminal size={36} />
            <span>01</span>
          </div>
          <AgentName agent={ranked[0]} onClick={() => onSelect(ranked[0])} />
          <strong
            className={`leader-roi ${roi(ranked[0]) >= 0 ? "positive" : "negative"}`}
          >
            {pct(roi(ranked[0]))}
          </strong>
          <p>ROI NET · {euro(nav(ranked[0]))}</p>
          <div className="spotlight-bottom">
            <span>Dernier du classement</span>
            <strong>
              {ranked.at(-1)?.id} {ranked.at(-1)?.name}
            </strong>
            <span className="negative">{pct(roi(ranked.at(-1)!))}</span>
          </div>
        </section>
      </div>
      <Leaderboard state={state} onSelect={onSelect} compact />
      <div className="bottom-grid">
        <section className="panel">
          <div className="panel-heading">
            <h2>
              <Radio size={16} /> Derniers mouvements
            </h2>
            <button
              className="text-button"
              onClick={() => onPage("Live activity")}
            >
              Tout voir <ChevronRight size={14} />
            </button>
          </div>
          <Feed state={state} limit={4} />
        </section>
        <section className="panel experiment-note">
          <span className="eyebrow">LES RÈGLES DU JEU</span>
          <h2>
            Le marché décide.
            <br />
            Les agents s'adaptent.
          </h2>
          <p>
            5 stratégies, 2 niveaux de capital. Aucun levier, aucun wallet.
            Chaque décision laisse une trace.
          </p>
          <div>
            <span>
              10 € <small>× 5 AGENTS</small>
            </span>
            <span>
              50 € <small>× 5 AGENTS</small>
            </span>
            <span>
              168 h <small>UNE COMPÉTITION</small>
            </span>
          </div>
        </section>
      </div>
    </>
  );
}
function Performance({ state }: { state: State }) {
  const bars = state.agents.map((a) => ({
    name: a.id,
    cash: Number(a.wallet.cash) / Number(state.fx.usd_per_eur),
    invested: Math.max(
      0,
      nav(a) - Number(a.wallet.cash) / Number(state.fx.usd_per_eur),
    ),
  }));
  return (
    <>
      <PageTitle
        eyebrow="PERFORMANCE LAB"
        title="Chaque stratégie laisse une courbe."
        text="Capital, rendement et risque à partir des valorisations enregistrées."
      />
      <section className="panel">
        <div className="panel-heading">
          <h2>Évolution du capital</h2>
          <span className="subtle">EUR · TAUX INITIAL</span>
        </div>
        <EquityChart state={state} />
        <div className="chart-legend">
          {state.agents.map((a, i) => (
            <span key={a.id}>
              <i style={{ background: colors[i] }} />
              {a.id} {a.name}
            </span>
          ))}
        </div>
      </section>
      <section className="panel">
        <div className="panel-heading">
          <h2>Rendement normalisé</h2>
          <span className="subtle">BASE 0 %</span>
        </div>
        <EquityChart state={state} normalized />
      </section>
      <div className="bottom-grid">
        <section className="panel">
          <div className="panel-heading">
            <h2>Liquidités et valeur investie</h2>
          </div>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={bars}>
              <CartesianGrid stroke="#242a33" vertical={false} />
              <XAxis dataKey="name" stroke="#718091" />
              <YAxis stroke="#718091" />
              <Tooltip
                contentStyle={{
                  background: "#141a22",
                  border: "1px solid #303943",
                }}
              />
              <Legend />
              <Bar
                dataKey="cash"
                name="Disponible €"
                stackId="a"
                fill="#c9f36c"
              />
              <Bar
                dataKey="invested"
                name="Liquidable €"
                stackId="a"
                fill="#637b98"
              />
            </BarChart>
          </ResponsiveContainer>
        </section>
        <section className="panel">
          <div className="panel-heading">
            <h2>Comparaison des cinq stratégies</h2>
          </div>
          <div className="strategy-rows">
            {["HUNTER", "SPRINTER", "ANALYST", "VALUE", "CONTRARIAN"].map(
              (name) => {
                const pair = state.agents.filter((a) => a.name === name);
                return (
                  <div key={name}>
                    <strong>{name}</strong>
                    <span>
                      {pair.map((a) => `${a.id} ${pct(roi(a))}`).join(" / ")}
                    </span>
                  </div>
                );
              },
            )}
          </div>
        </section>
      </div>
      <section className="panel">
        <div className="panel-heading">
          <h2>Résultats et risque</h2>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>AGENT</th>
                <th>RÉALISÉ €</th>
                <th>NON RÉALISÉ €</th>
                <th>DRAWDOWN MAX.</th>
                <th>P&L RÉALISÉ PAR CATÉGORIE (QUOTE)</th>
              </tr>
            </thead>
            <tbody>
              {state.agents.map((a) => (
                <tr key={a.id}>
                  <td>
                    {a.id} {a.name}
                  </td>
                  <td>
                    {euro(
                      Number(a.snapshot?.realized || 0) /
                        Number(state.fx.usd_per_eur),
                    )}
                  </td>
                  <td>
                    {euro(
                      Number(a.snapshot?.unrealized || 0) /
                        Number(state.fx.usd_per_eur),
                    )}
                  </td>
                  <td>{pct(-Number(a.stats.max_drawdown))}</td>
                  <td>
                    {Object.entries(a.stats.categories)
                      .map(([k, v]) => `${k}: ${num(v)}`)
                      .join(" · ") || "Aucune sortie réalisée"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
function AgentDetail({ a, state }: { a: Agent; state: State }) {
  return (
    <>
      <PageTitle
        eyebrow={`${a.id} / STRATEGY PROFILE`}
        title={a.name}
        text={`${a.initial_eur} EUR de capital fictif · ${a.dynamic ? "Objectif : croissance du portefeuille sur sept jours" : "Analyse sélective et protection du capital"}`}
      />
      <div className="kpi-grid">
        <Kpi
          label="VALEUR NETTE"
          value={euro(nav(a))}
          sub={a.snapshot?.valuation || "En attente du premier cycle"}
        />
        <Kpi
          label="ROI NET"
          value={pct(roi(a))}
          sub="Frais compris"
          positive={roi(a) >= 0}
        />
        <Kpi
          label="DISPONIBLE"
          value={euro(Number(a.wallet.cash) / Number(state.fx.usd_per_eur))}
          sub="Sans emprunt ni levier"
        />
        <Kpi
          label="MAX. DRAWDOWN"
          value={pct(-Number(a.stats.max_drawdown))}
          sub={`${a.stats.trades} trades · ${a.stats.closed} sorties / résolutions`}
        />
      </div>
      <section className="panel">
        <div className="panel-heading">
          <h2>Courbe individuelle</h2>
          <Badge agent={a} />
        </div>
        <EquityChart state={state} selected={a.id} />
      </section>
      <div className="bottom-grid">
        <section className="panel padded">
          <h2>Mandat stratégique</h2>
          <p className="prompt">{a.prompt}</p>
          <h3>Paramètres de risque</h3>
          <div className="key-values">
            {Object.entries(a.risk).map(([k, v]) => (
              <div key={k}>
                <span>{k}</span>
                <strong>{String(v)}</strong>
              </div>
            ))}
          </div>
        </section>
        <section className="panel padded">
          <h2>Mémoire persistante</h2>
          <p className="prompt">
            {a.memory.summary || "Aucune analyse enregistrée."}
          </p>
          <h3>Plan de sortie</h3>
          <p>{a.memory.exit_plan || "En attente de décision."}</p>
          <p className="subtle">
            {a.memory.calls || 0} sessions IA aujourd'hui{" "}
            {a.memory.paused_until &&
              `· suspension jusqu'au ${new Date(a.memory.paused_until).toLocaleString("fr-FR")}`}
          </p>
        </section>
      </div>
      <section className="panel">
        <div className="panel-heading">
          <h2>Positions ouvertes</h2>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>MARCHÉ</th>
                <th>OUTCOME</th>
                <th>QUANTITÉ</th>
                <th>COÛT QUOTE</th>
                <th>LIQUIDABILITÉ</th>
              </tr>
            </thead>
            <tbody>
              {Object.values(a.wallet.positions)
                .filter((p) => Number(p.quantity) > 0)
                .map((p) => (
                  <tr key={p.market_id + p.outcome}>
                    <td>
                      {state.markets[p.market_id]?.question || p.market_id}
                    </td>
                    <td>{p.outcome}</td>
                    <td>{num(p.quantity)}</td>
                    <td>{num(p.cost)}</td>
                    <td>
                      {a.snapshot?.stranded.includes(
                        `${p.market_id}:${p.outcome}`,
                      )
                        ? "Partielle / indisponible"
                        : "Carnet disponible"}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
        {!Object.values(a.wallet.positions).some(
          (p) => Number(p.quantity) > 0,
        ) && <p className="empty">Aucune position ouverte.</p>}
      </section>
      <section className="panel padded">
        <h2>Décisions récentes</h2>
        {[...a.decisions].reverse().map((d, i) => (
          <article className="decision" key={i}>
            <div>
              <span className="pill">
                {d.action} {d.outcome}
              </span>
              <time>{new Date(d.at).toLocaleString("fr-FR")}</time>
                <span>Edge vérifié {d.verified_edge === null ? "non estimé" : pct(d.verified_edge)}</span>
                {d.decision_kind === "EXPLORATION" && <span className="pill">Exploration · règle de participation</span>}
            </div>
            <h3>{state.markets[d.market_id]?.question || d.market_id}</h3>
            <p>{d.reasoning}</p>
            <p className="subtle">
              Confiance : {pct(d.confidence)} · P(YES) :{" "}
                {d.probability_basis === "UNESTIMATED" ? "non estimée" : pct(d.estimated_probability)} · {d.decision_status || d.action}{d.rejection && d.action !== "WAIT" && d.action !== "HOLD" ? ` · ${d.rejection}` : ""}
            </p>
            <p>Sortie : {d.exit_plan}</p>
            <p>Risques : {d.risk_factors.join(" · ")}</p>
            {d.sources.map((s) => (
              <a key={s} href={s} target="_blank" rel="noreferrer">
                {s} <External size={12} />
              </a>
            ))}
          </article>
        ))}
      </section>
      <section className="panel">
        <div className="panel-heading">
          <h2>Transactions récentes · achats et sorties</h2>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>HEURE</th>
                <th>ACTION</th>
                <th>MARCHÉ</th>
                <th>STATUT</th>
                <th>FILLS OBSERVÉS</th>
              </tr>
            </thead>
            <tbody>
              {[...a.orders].reverse().map((o) => (
                <tr key={o.id}>
                  <td>{time(o.at)}</td>
                  <td>
                    {o.action} {o.outcome}
                  </td>
                  <td>{o.market_id}</td>
                  <td>
                    {o.status} {o.reason}
                  </td>
                  <td>
                    {o.execution?.fills
                      .map(
                        (f) =>
                          `${num(f.quantity)} @ ${f.price} · frais ${f.fee}`,
                      )
                      .join("; ") || "Aucun fill"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
function Markets({ state }: { state: State }) {
  const [search, setSearch] = useState("");
  return (
    <>
      <PageTitle
        eyebrow="PUBLIC MARKET DATA"
        title="Le terrain de jeu."
        text="Cotations observées, contraintes réelles et expositions des agents."
      />
      <label className="search">
        <Search size={16} />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Rechercher un marché…"
        />
      </label>
      <div className="markets-grid">
        {Object.values(state.markets)
          .filter((m) =>
            m.question.toLowerCase().includes(search.toLowerCase()),
          )
          .map((m) => (
            <section key={m.id} className="panel market-card">
              <div className="market-top">
                <span className="pill">{m.category}</span>
                <span>
                  {m.version} ·{" "}
                  {m.resolved ? "RÉSOLU" : m.active ? "ACTIF" : "FERMÉ"}
                </span>
              </div>
              <h2>{m.question}</h2>
              <p className="market-desc">{m.description}</p>
              <div className="quotes">
                {["YES", "NO"].map((o) => {
                  const b = m.books[o],
                    asks = b?.asks.map((l) => Number(l.price)) || [],
                    bids = b?.bids.map((l) => Number(l.price)) || [];
                  return (
                    <div key={o}>
                      <small>{o} · BID / ASK</small>
                      <strong>
                        {bids.length ? Math.max(...bids).toFixed(3) : "—"} /{" "}
                        {asks.length ? Math.min(...asks).toFixed(3) : "—"}
                      </strong>
                      <span>
                        Min {b?.minimum || "—"} actions · tick {b?.tick || "—"}
                        <br />
                        Frais : rate {b?.fee_rate || "—"}
                        <br />
                        {b
                          ? new Date(b.observed_at).toLocaleString("fr-FR")
                          : "Carnet indisponible"}
                      </span>
                    </div>
                  );
                })}
              </div>
              <div className="key-values">
                <div>
                  <span>Liquidité / volume 24 h</span>
                  <strong>
                    {num(m.liquidity)} / {num(m.volume)}
                  </strong>
                </div>
                <div>
                  <span>Échéance</span>
                  <strong>
                    {m.end_at
                      ? new Date(m.end_at).toLocaleString("fr-FR")
                      : "Non fournie"}
                  </strong>
                </div>
                <div>
                  <span>Agents exposés</span>
                  <strong>
                    {state.agents
                      .filter((a) =>
                        Object.values(a.wallet.positions).some(
                          (p) => p.market_id === m.id && Number(p.quantity) > 0,
                        ),
                      )
                      .map((a) => a.id)
                      .join(", ") || "Aucun"}
                  </strong>
                </div>
              </div>
              {state.mode === "live" && (
                <a
                  className="text-button"
                  href={m.url || `https://polymarket.com/event/${m.slug}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  Voir sur Polymarket <External size={14} />
                </a>
              )}
            </section>
          ))}
      </div>
      {!Object.keys(state.markets).length && (
        <div className="panel empty">
          Aucun marché disponible. Consultez les alertes système.
        </div>
      )}
    </>
  );
}
function PageTitle({
  eyebrow,
  title,
  text,
}: {
  eyebrow: string;
  title: string;
  text: string;
}) {
  return (
    <div className="intro">
      <div className="eyebrow">{eyebrow}</div>
      <h1>{title}</h1>
      <p>{text}</p>
    </div>
  );
}
function App() {
  const [page, setPage] = useState("Overview"),
    [demo, setDemo] = useState(
      new URLSearchParams(location.search).get("mode") === "demo",
    ),
    [selected, setSelected] = useState("A1"),
    [clock, setClock] = useState(Date.now()),
    [start, setStart] = useState(false);
  const { state, error, loading } = useCompetition(demo);
  useEffect(() => {
    const id = setInterval(() => setClock(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  const remaining = state
    ? Math.max(0, new Date(state.end_at).getTime() - clock)
    : 168 * 3600000;
  const elapsed = state
    ? Math.min(
        168,
        Math.max(0, (clock - new Date(state.started_at).getTime()) / 3600000),
      )
    : 0;
  const stale =
    !!state?.last_market_sync &&
    clock - new Date(state.last_market_sync).getTime() > 20 * 60000;
  const selectAgent = (a: Agent) => {
    setSelected(a.id);
    setPage("Agents");
  };
  const download = () => {
    if (!state) return;
    const blob = new Blob([JSON.stringify(state, null, 2)], {
        type: "application/json",
      }),
      url = URL.createObjectURL(blob),
      a = document.createElement("a");
    a.href = url;
    a.download = `${state.id}-dashboard.json`;
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <div className="app">
      <aside className="sidebar">
        <a className="brand" href="/" aria-label="PROJECT SURVIVAL">
          <span className="brand-icon">
            <Terminal size={22} />
          </span>
          <span>
            PROJECT
            <strong>
              SURVIVAL<span className="lime">.</span>
            </strong>
          </span>
        </a>
        <div className="sidebar-label">CONTROL ROOM</div>
        <nav>
          {navItems.map(({ label, icon: Icon }) => (
            <button
              key={label}
              className={label === page ? "active" : ""}
              onClick={() => setPage(label)}
            >
              <Icon size={17} />
              {label}
              {label === "Live activity" && <span className="live-dot" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="paper-badge">
            <Shield size={18} />
            <div>
              <strong>Paper trading only</strong>
              <small>Aucun argent réel en jeu</small>
            </div>
          </div>
          <button
            className={`demo-toggle ${demo ? "demo-on" : ""}`}
            onClick={() => {
              setDemo(!demo);
              history.replaceState({}, "", demo ? "/" : "/?mode=demo");
            }}
          >
            <FlaskConical size={15} />
            {demo ? "Quitter la démonstration" : "Mode démonstration"}
            <span className="toggle">
              <i />
            </span>
          </button>
          <div className="version">
            <span>PROJECT SURVIVAL</span>
            <span>v1.0</span>
          </div>
        </div>
      </aside>
      <div className="workspace">
        <header>
          <div className="breadcrumbs">
            Workspace <ChevronRight size={12} />
            <strong>{page}</strong>
          </div>
          <div className="header-right">
            <span
              className={`connection ${demo ? "warning" : error || stale ? "negative" : "positive"}`}
            >
              <span className="live-dot" />
              {demo
                ? "DEMO · SYNTHETIC"
                : loading
                  ? "CONNEXION…"
                  : error
                    ? "NON CONNECTÉ"
                    : state
                      ? stale
                        ? "DONNÉES PÉRIMÉES"
                        : "POLYMARKET DATA"
                      : "PRÊT À CONFIGURER"}
            </span>
            <button
              className="icon-button"
              onClick={download}
              disabled={!state}
              title="Exporter la vue JSON"
              aria-label="Exporter la vue JSON"
            >
              <Download size={16} />
            </button>
            <span className="user-avatar">PS</span>
          </div>
        </header>
        <div className="competition-bar">
          <div>
            <span className="season">EXPERIMENT 001</span>
            <strong>10 AI Agents. 7 Days. One Winner.</strong>
          </div>
          <div className="countdown">
            <Clock3 size={15} />
            <span>{state ? "TEMPS RESTANT" : "DURÉE DE LA COMPÉTITION"}</span>
            <strong>
              {String(Math.floor(remaining / 3600000)).padStart(3, "0")}
              <small>h</small>{" "}
              {String(Math.floor(remaining / 60000) % 60).padStart(2, "0")}
              <small>m</small>{" "}
              {String(Math.floor(remaining / 1000) % 60).padStart(2, "0")}
              <small>s</small>
            </strong>
          </div>
          <div className="progress-track">
            <span style={{ width: `${(elapsed / 168) * 100}%` }} />
          </div>
        </div>
        <main>
          {demo && (
            <div className="alert demo-alert">
              <FlaskConical size={16} />
              <span>
                DÉMONSTRATION — données synthétiques, décisions déterministes,
                aucun appel IA. Base isolée.
              </span>
              <button
                className="icon-button"
                aria-label="Fermer la démonstration"
                onClick={() => {
                  setDemo(false);
                  history.replaceState({}, "", "/");
                }}
              >
                <X size={14} />
              </button>
            </div>
          )}
          {error && (
            <div className="alert">
              <Database size={16} />
              <span>{error}</span>
            </div>
          )}
          {stale && (
            <div className="alert">
              Dernière collecte trop ancienne. Les valeurs affichées ne sont pas
              des cotations actuelles.
            </div>
          )}
          {state?.report && (
            <div className="final-banner">
              <Trophy size={22} />
              <div>
                <strong>
                  Compétition terminée · vainqueur ROI :{" "}
                  {state.report.roi_winner}
                </strong>
                <p>
                  Vainqueur bénéfice absolu : {state.report.absolute_winner}.{" "}
                  {state.report.incomplete_valuation
                    ? "Valorisation incomplète : classement par borne basse."
                    : ""}{" "}
                  Retard de clôture :{" "}
                  {Math.round(state.report.close_delay_seconds)} s.
                </p>
                <small>{state.report.limitation}</small>
              </div>
            </div>
          )}
          {state ? (
            page === "Overview" ? (
              <Overview state={state} onSelect={selectAgent} onPage={setPage} />
            ) : page === "Leaderboard" ? (
              <>
                <PageTitle
                  eyebrow="THE RANKING"
                  title="Une seule place au sommet."
                  text="Classement par rendement net. Les égalités sont départagées par identifiant."
                />
                <Leaderboard state={state} onSelect={selectAgent} />
              </>
            ) : page === "Performance" ? (
              <Performance state={state} />
            ) : page === "Agents" ? (
              <>
                <div className="agent-tabs">
                  {state.agents.map((a) => (
                    <button
                      className={a.id === selected ? "selected" : ""}
                      key={a.id}
                      onClick={() => setSelected(a.id)}
                    >
                      {a.id} <span>{a.name}</span>
                    </button>
                  ))}
                </div>
                <AgentDetail
                  a={
                    state.agents.find((a) => a.id === selected) ||
                    state.agents[0]
                  }
                  state={state}
                />
              </>
            ) : page === "Live activity" ? (
              <>
                <PageTitle
                  eyebrow="LIVE OPERATIONS"
                  title="Chaque décision. Chaque mouvement."
                  text="Événements persistés, actualisés automatiquement via Supabase Realtime."
                />
                <section className="panel">
                  <Feed state={state} />
                </section>
              </>
            ) : (
              <Markets state={state} />
            )
          ) : (
            <>
              <PageTitle
                eyebrow="AUTONOMOUS TRADING EXPERIMENT"
                title="PROJECT SURVIVAL"
                text="10 AI Agents. 7 Days. One Winner."
              />
              <div className="setup-panel panel">
                <div className="setup-emblem">
                  <Terminal size={48} />
                </div>
                <h2>
                  {loading
                    ? "Connexion à l’arène…"
                    : "L’arène attend le signal."}
                </h2>
                <p>
                  Connectez Supabase et lancez explicitement START pour ouvrir
                  la compétition de 168 heures. Aucun déploiement ne déclenche
                  de transaction.
                </p>
                <button className="primary" onClick={() => setStart(true)}>
                  <Play size={15} /> Préparer le lancement
                </button>
                <button className="text-button" onClick={() => setDemo(true)}>
                  Explorer le cycle de démonstration <ChevronRight size={14} />
                </button>
                <div className="setup-rules">
                  <span>10 agents indépendants</span>
                  <span>300 € fictifs</span>
                  <span>Aucun wallet</span>
                </div>
              </div>
            </>
          )}
          <footer>
            <span>
              <Shield size={12} /> Simulation financière · aucune garantie de
              performance future
            </span>
            <span>
              {state?.last_market_sync
                ? `Dernière collecte : ${new Date(state.last_market_sync).toLocaleString("fr-FR")}`
                : demo
                  ? "Source : fixtures synthétiques"
                  : "En attente de première collecte"}
            </span>
          </footer>
          {state && (
            <details className="fx-method">
              <summary>Méthode de conversion et valorisation</summary>
              <p>
                {state.fx.method} · EUR/USD {state.fx.usd_per_eur} · référence{" "}
                {state.fx.reference_date}. Les gains de trading excluent les
                variations FX. Les positions sont valorisées au bid liquidable,
                après frais ; les quantités non liquidables sont signalées et
                valorisées à zéro pour une borne basse. Win rate : sorties
                partielles et résolutions rentables / sorties et résolutions.
              </p>
            </details>
          )}
        </main>
      </div>
      {start && (
        <div className="modal-backdrop" onClick={() => setStart(false)}>
          <section
            className="modal panel padded"
            role="dialog"
            aria-modal="true"
            aria-label="Lancement explicite"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="close icon-button"
              aria-label="Fermer"
              onClick={() => setStart(false)}
            >
              <X size={18} />
            </button>
            <span className="eyebrow">EXPLICIT START</span>
            <h2>Ouvrir la compétition</h2>
            <p>
              Après les migrations et la configuration des secrets, utilisez
              GitHub Actions → SURVIVAL cycles → Run workflow → action{" "}
              <strong>start</strong>.
            </p>
            <p>Ou exécutez côté serveur :</p>
            <pre>python -m survival.cli start</pre>
            <p>
              Le serveur fige le taux de référence et enregistre started_at +
              168 heures. Le dashboard ne possède aucun secret permettant de
              modifier les comptes.
            </p>
            {import.meta.env.VITE_GITHUB_START_URL && (
              <a
                className="primary"
                target="_blank"
                rel="noreferrer"
                href={import.meta.env.VITE_GITHUB_START_URL}
              >
                Ouvrir GitHub Actions <External size={14} />
              </a>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
