// Strava webhook receiver (a Cloudflare Worker): a new activity on Strava starts the refresh workflow,
// which ingests it from Garmin and has Claude review it. See "Refresh after a workout" in the README.
//
// Strava does not sign its events, so an event only counts when it names this subscription and
// this athlete. The worst a forged one can do is start one extra refresh: the workflow queues
// runs one at a time and a run without a new workout changes nothing.
//
// Settings (wrangler secret put <NAME>):
//   STRAVA_VERIFY_TOKEN    any random string, also passed when creating the subscription
//   STRAVA_ATHLETE_ID      your Strava athlete id
//   STRAVA_SUBSCRIPTION_ID the id Strava returns when the subscription is created
//   GITHUB_TOKEN           fine-grained token for this repository with "Actions: Read and write"
// and in wrangler.toml: GITHUB_REPO (owner/name) and WORKFLOW (the workflow file).

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname !== '/strava') return new Response('Not found', { status: 404 });
    if (request.method === 'GET') return verify(url, env);
    if (request.method !== 'POST') return new Response('Method not allowed', { status: 405 });

    let event;
    try { event = await request.json(); } catch { return new Response('Bad request', { status: 400 }); }
    // Strava wants a 200 within two seconds and retries otherwise, so dispatch after answering.
    if (isNewWorkout(event, env)) ctx.waitUntil(dispatch(event, env));
    return new Response('ok');
  },
};

// Subscription handshake: echo the challenge when the verify token matches.
function verify(url, env) {
  const p = url.searchParams;
  if (p.get('hub.mode') !== 'subscribe' || p.get('hub.verify_token') !== env.STRAVA_VERIFY_TOKEN) {
    return new Response('Forbidden', { status: 403 });
  }
  return Response.json({ 'hub.challenge': p.get('hub.challenge') });
}

function isNewWorkout(event, env) {
  return event?.object_type === 'activity'
    && event.aspect_type === 'create'
    && String(event.owner_id) === String(env.STRAVA_ATHLETE_ID)
    && String(event.subscription_id) === String(env.STRAVA_SUBSCRIPTION_ID);
}

async function dispatch(event, env) {
  const res = await fetch(`https://api.github.com/repos/${env.GITHUB_REPO}/actions/workflows/${env.WORKFLOW}/dispatches`, {
    method: 'POST',
    headers: {
      authorization: `Bearer ${env.GITHUB_TOKEN}`,
      accept: 'application/vnd.github+json',
      'x-github-api-version': '2022-11-28',
      'user-agent': 'garminreader-strava-webhook',
    },
    body: JSON.stringify({ ref: 'main', inputs: { reason: `New Strava activity ${event.object_id}` } }),
  });
  if (!res.ok) console.error(`Workflow dispatch failed: ${res.status} ${await res.text()}`);
  else console.log(`Refresh started for Strava activity ${event.object_id}`);
}
