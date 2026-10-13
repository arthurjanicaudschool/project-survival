// Independent free scheduler. Only reads public state and dispatches paper cycles.
export default {
  async scheduled(_event, env, ctx) { ctx.waitUntil(tick(env)); },
  async fetch() { return Response.json({service:"PROJECT SURVIVAL watchdog",paper_only:true}); }
};
export async function tick(env) {
  const response=await fetch(`${env.SUPABASE_URL}/rest/v1/dashboard_states?experiment_id=eq.${encodeURIComponent(env.EXPERIMENT_ID)}&select=payload`,
    {headers:{apikey:env.SUPABASE_ANON_KEY,Authorization:`Bearer ${env.SUPABASE_ANON_KEY}`}});
  if(!response.ok)throw new Error(`Public state unavailable: ${response.status}`);
  const rows=await response.json();const state=rows[0]?.payload;
  if(!state || state.status==="FINISHED")return;
  const age=Date.now()-Date.parse(state.inflight?state.updated_at:state.health?.completed_at || state.updated_at);
  if(age<12*60000 || state.inflight && age<25*60000)return;
  const result=await fetch(`https://api.github.com/repos/${env.GITHUB_REPOSITORY}/actions/workflows/cycle.yml/dispatches`,
    {method:"POST",headers:{Authorization:`Bearer ${env.GITHUB_SCHEDULER_TOKEN}`,Accept:"application/vnd.github+json","User-Agent":"ProjectSurvivalIndependentWatchdog","Content-Type":"application/json"},
     body:JSON.stringify({ref:"main",inputs:{action:"cycle",source:"cloudflare-watchdog"}})});
  if(result.status!==204)throw new Error(`Dispatch failed: ${result.status}`);
  console.log(JSON.stringify({event:"paper_cycle_dispatched",at:new Date().toISOString()}));
}
